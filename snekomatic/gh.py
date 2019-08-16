"""

A simple abstraction for writing Github Apps.

Basic setup:

  gh_app = GithubApp(...secrets and stuff...)

  @gh_app.route("issue", action="created")
  @gh_app.route("pull_request", action="created")
  async def handler(event_type, payload, gh_client):
      assert event_type in ["issue", "pull_request"]
      assert payload["action"] == "created"
      # 'gh_client' is a gidgethub-style github API client that automatically
      # uses the right credentials for this webhook event.

Integrate into webapp:

  @quart_app.route("/webhook/github", methods=["POST"])
  async def handler():
      headers = request.headers
      body = await request.get_body()
      await gh_app.dispatch_webhook(headers, body)
      return ""

If you want to make API requests spontaneously, not in response to a
webhook, then use one of these:

  client = gh_app.app_client
  client = gh_app.client_for(installation_id)

This should probably be split off into its own library eventually...

Interesting facts about this code, compared to octomachinery:

* We don't have any support for Github Actions
* This code should work with any of trio/asyncio/curio
* Doesn't try to "own" the event loop or web server -> can be integrated
  into a larger web app
* More robust auth token handling (better clock handling; checks for
  expiration before each request rather than just when a new webhook
  arrives)
* Insists on using webhook secret, since anything else is totally insecure
* No utility functions that call yaml.load and thus execute arbitrary code
* Almost 10x simpler (as measured by lines-of-code)

Many thanks to Sviat for octomachinery though, because I would never have
figured out how to do any of this stuff without studying his code.

"""

from collections import defaultdict
import os
from typing import Mapping, Tuple

import anyio
import asks
import attr
import cachetools
from gidgethub.sansio import Event, accept_format
import gidgethub.abc
from glom import glom
import jwt
import pendulum

__all__ = ["GithubApp"]

# XX TODO: should we catch exceptions in webhook handlers, the same way flask
# etc. catch exceptions in request handlers? right now the first exception
# leaks out of dispatch_webhook and cancels the running of other handlers

# XX octomachinery's preview_version= argument is pretty handy, should we
# adopt it? maybe push upstream to gidgethub?

# Also, we're fighting against gidgethub's structure some here... we should
# talk to Brett about how to make this easier.

# Assume that there might be this much offset between our clock at the time of
# submitting a request and Github's clock at the time of processing the
# request, or vice-versa.
MAX_CLOCK_SKEW = pendulum.Duration(minutes=1)


def _too_close_for_comfort(expires_at):
    return pendulum.now() + MAX_CLOCK_SKEW > expires_at


def _env_fallback(name, passed):
    if passed is not None:
        return passed
    envvar_name = f"GITHUB_{name.upper()}"
    if envvar_name not in os.environ:
        raise RuntimeError(
            f"you must either pass {name} or set {envvar_name}"
        )
    return os.environ[envvar_name]


def _all_match(data, restrictions):
    for key, value in restrictions.items():
        if key not in data or data[key] != value:
            return False
    return True


# This should maybe move into gidgethub
class BaseGithubClient(gidgethub.abc.GitHubAPI):
    def __init__(self, session, *args, **kwargs):
        self._session = session
        super().__init__(*args, **kwargs)

    async def _request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes = b"",
    ) -> Tuple[int, Mapping[str, str], bytes]:
        response = await self._session.request(
            method, url, headers=headers, data=body
        )
        # asks stores headers in a regular dict. They're probably lowercase
        # already, but let's be 100% certain.
        lower_headers = {
            key.lower(): value for (key, value) in response.headers.items()
        }
        return response.status_code, lower_headers, response.content

    # Why does gidgethub make this mandatory? it's not used for anything
    async def sleep(self, seconds):
        await anyio.sleep(seconds)


@attr.s
class SegmentedCacheOverlay:
    _underlying = attr.ib()
    _segment = attr.ib()

    def __getitem__(self, key):
        return self._underlying[self._segment, key]

    def __setitem__(self, key, value):
        self._underlying[self._segment, key] = value


class AppGithubClient(BaseGithubClient):
    def __init__(self, app):
        self.app = app
        cache = SegmentedCacheOverlay(app._cache, None)
        super().__init__(app._session, requester=app.user_agent, cache=cache)

    async def _make_request(self, *args, **kwargs):
        now = pendulum.now()
        jwt_app_token = jwt.encode(
            {
                "iat": (now - MAX_CLOCK_SKEW).int_timestamp,
                "exp": (now + MAX_CLOCK_SKEW).int_timestamp,
                "iss": self.app.app_id,
            },
            key=self.app._private_key,
            algorithm="RS256",
        )
        jwt_app_token = jwt_app_token.decode("ascii")
        kwargs["oauth_token"] = None
        kwargs["jwt"] = jwt_app_token
        return await super()._make_request(*args, **kwargs)


class InstallationGithubClient(BaseGithubClient):
    def __init__(self, app, installation_id):
        self.app = app
        self.installation_id = installation_id
        cache = SegmentedCacheOverlay(app._cache, installation_id)
        super().__init__(app._session, requester=app.user_agent, cache=cache)

    async def _make_request(self, *args, **kwargs):
        token = await self.app._get_token(self.installation_id)
        kwargs["oauth_token"] = token
        kwargs["jwt"] = None
        return await super()._make_request(*args, **kwargs)


@attr.s
class CachedInstallationToken:
    token = attr.ib(default="")
    # pendulum.DateTime
    expires_at = attr.ib(default=pendulum.datetime(1900, 1, 1))
    # if a refresh is already in progress, an anyio.Event
    # otherwise, None
    refresh_event = attr.ib(default=None)


@attr.s(frozen=True)
class Route:
    async_fn = attr.ib()
    restrictions = attr.ib()


class GithubApp:
    def __init__(
        self,
        *,
        session=None,
        app_id=None,
        user_agent=None,
        private_key=None,
        webhook_secret=None,
        # XX Completely untuned; maybe this is too big, or too small.
        cache_size=500,
    ):
        if session is None:
            # We don't really need to limit simultaneous connections... we're
            # not going to overwhelm github's frontend servers.
            session = asks.Session(connections=100)
        self._session = session
        self.app_id = _env_fallback("app_id", app_id)
        self.user_agent = _env_fallback("user_agent", user_agent)
        self._private_key = _env_fallback("private_key", private_key)
        self._webhook_secret = _env_fallback("webhook_secret", webhook_secret)
        self._installation_tokens = defaultdict(CachedInstallationToken)
        # event_type -> [Route(...), Route(...), ...]
        self._routes = defaultdict(list)
        self._cache = cachetools.LRUCache(cache_size)
        self.app_client = AppGithubClient(self)

    def client_for(self, installation_id):
        return InstallationGithubClient(self, installation_id)

    async def _get_token(self, installation_id):
        cit = self._installation_tokens[installation_id]

        while _too_close_for_comfort(cit.expires_at):
            print(f"{installation_id}: Token is expired or will be soon")
            if cit.refresh_event is not None:
                print(
                    f"{installation_id}: Renewal already in progress; waiting"
                )
                await cit.refresh_event.wait()
            else:
                print(f"{installation_id}: Renewing now")
                cit.refresh_event = anyio.create_event()
                try:
                    response = await self.app_client.post(
                        "/app/installations/{installation_id}/access_tokens",
                        url_vars={"installation_id": installation_id},
                        accept=accept_format(version="machine-man-preview"),
                        data={},
                    )
                    cit.token = response["token"]
                    cit.expires_at = pendulum.parse(response["expires_at"])
                    assert not _too_close_for_comfort(cit.expires_at)
                    print(f"{installation_id}: Renewed successfully")
                finally:
                    # Make sure that even if we get cancelled, any other tasks
                    # will still wake up (and can retry the operation)
                    await cit.refresh_event.set()
                    cit.refresh_event = None

        return cit.token

    def add(self, async_fn, event_type, **restrictions):
        if len(restrictions) > 1:
            raise TypeError("At most one restriction is allowed (for now)")
        self._routes[event_type].append(Route(async_fn, restrictions))

    def route(self, event_type, **restrictions):
        def decorator(async_fn):
            self.add(async_fn, event_type, **restrictions)
            return async_fn

        return decorator

    async def dispatch_webhook(self, headers, body):
        event = Event.from_http(headers, body, secret=self._webhook_secret)
        print("Got valid GH webhook with delivery id:", event.delivery_id)
        # Wait a bit to give Github's eventual consistency time to catch up
        await anyio.sleep(1)
        installation_id = glom(event.data, "installation.id")
        client = self.client_for(installation_id)
        for route in self._routes[event.event]:
            if _all_match(event.data, route.restrictions):
                print(f"Routing to {route.async_fn!r}")
                await route.async_fn(event.event, event.data, client)
        try:
            limit = client.rate_limit.remaining
        except AttributeError:
            pass
        else:
            print(f"Rate limit for install {installation_id}: {limit}")
