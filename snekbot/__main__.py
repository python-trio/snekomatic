# Make sure that print's are flushed immediately so heroku's logging
# infrastructure can see them.
import sys
sys.stdout.reconfigure(line_buffering=True)

import os
import pendulum
import trio
from glom import glom
import asks
import hypercorn
import hypercorn.trio
import quart
from quart import request, g
from quart_trio import QuartTrio
import json
import traceback
from gidgethub.sansio import Event, accept_format
import gidgethub.abc
import jwt

# TODO: should probably be a config variable!
USER_AGENT = "njsmith/snekbot"

# octomachinery's RawGithubAPI subclasses and extra features:
# - have to initialize with their token class, which is a discriminated union
#   for oauth and jwt tokens, and then overrides _make_request to
#   automatically pass it to all methods
# - tries to hack the aiohttp implementation to use a persistent session, but
#   this doesn't even make sense, because the persistent session is already
#   mandatory
# - wraps all methods to take preview_version argument

# I don't care about the token stuff, totally unneeded
# ditto for sessions
# returning DotDict instead of dict would be nice though!
# ...or just use glom
# the preview_version thing is nice enough I guess

# we should stash the delivery id in a contextvar and include it in logging
# also maybe structlog? eh print is so handy for now

# maybe to factor this:
# - asks/anyio based client, works on trio/curio/asyncio
# - a way to pass in a gidgethub router + asks session + secrets, and get back
#   a quart response handler, which you get to drop into your quart app.
#   (asyncio or trio)
#   - well, we do use trio.Event. could use anyio.Event.
# - or maybe pass in a quart app + url and have the handler automatically set
#   up? kinda weird that it's not global... I guess it could be global if
#   we're okay with lazily initializing the Session!
# - or we could just have a webhook dispatcher where you pass in headers+body
#   and it does its thing

# FIXME: the GithubAPI object should check the token expiration on *every*
# call, not just when it's created!
# I guess override _make_request to ignore jwt/oauth_token args, and instead
# start by fetching a token and then calling super()

class GithubAPI(gidgethub.abc.GithubAPI):
    def __init__(self, session, *args, **kwargs):
        self._session = session
        super().__init__(*args, **kwargs)

    async def _request(
            self,
            method: str,
            url: str,
            headers: Mapping[str, str],
            body: bytes = b''
    ) -> Tuple[int, Mapping[str, str], bytes]:
        response = await self._session.request(
            method, url, headers=headers, data=body
        )
        lower_headers = {
            key.lower(): value for (key, value) in response.headers.items()
        }
        return response.status_code, lower_headers, await response.read()

    # Why does gidgethub make this mandatory? it's silly
    async def sleep(self, seconds):
        await trio.sleep(seconds)


MAX_CLOCK_SKEW = pendulum.duration(minutes=1)

class InstallationClientCache:
    def __init__(self, session):
        self._session = session
        # install -> token, expiration
        self._tokens = {}
        # install -> trio.Event
        self._in_progress = {}

    def _too_close_for_comfort(self, expiration):
        return pendulum.now() + MAX_CLOCK_SKEW > expiration

    async def _renew(self, install_id):
        if install_id in self._in_progress:
            print(f"Renewal for {install_id} already in progress... waiting")
            await self._in_progress[install_id].wait()
        else:
            print(f"Renewing {install_id}")
            renew_finished = trio.Event()
            self._in_progress[install_id] = renew_finished
            # make jwt
            now = pendulum.now()
            payload = {
                "iat": (now - MAX_CLOCK_SKEW).int_timestamp,
                "exp": (now + MAX_CLOCK_SKEW).int_timestamp,
                "iss": os.environ["GITHUB_APP_IDENTIFIER"],
            }
            jwt_token = jwt.encode(
                payload,
                key=os.environ["GITHUB_PRIVATE_KEY"],
                algorithm="RS256",
            ).decode("ascii")
            gh = GithubAPI(self._session, requestor=USER_AGENT)
            response = await gh.post(
                "/app/installations{/installation_id}/access_tokens",
                url_vars=dict(installation_id=install_id),
                accept=accept_format(version="machine-man-preview"),
                jwt=jwt_token,
            )
            token = glom(response, "token")
            expiration = pendulum.parse(glom(response, "expires_at"))
            assert not self._too_close_for_comfort(expiration)
            self._tokens[install_id] = (token, expiration)
            renew_finished.set()
            del self._in_progress[install_id]

    async def get(self, install_id):
        print(f"Getting token for install_id {install_id}")
        while True:
            if install_id not in self._tokens:
                await self._renew(install_id)
                continue
            token, expiration = self._tokens[install_id]
            if self._too_close_for_comfort(expiration):
                await self._renew(install_id)
                continue
            return GithubAPI(self._session, requestor=USER_AGENT, oauth=token)

app = QuartTrio("snekbot")

if "SENTRY_DSN" in os.environ:
    import sentry_sdk
    sentry_sdk.init(os.environ["SENTRY_DSN"])

    @quart.got_request_exception.connect
    async def error_handler(_, *, exception):
        if isinstance(exception, Exception):
            print(f"Logging error to sentry: {exception!r}")
            sentry_sdk.capture_exception(exception)
        else:
            print(f"NOT logging error to sentry: {exception!r}")

@app.route("/")
async def index():
    return "Hi! 🐍🐍🐍"

@app.route("/oops")
async def oops():
    raise RuntimeError("roh uh")

@app.route("/webhook/github", methods=["POST"])
async def webhook_github():
    body = await request.get_data()
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
    event = Event.from_http(request.headers, body, secret=secret)
    print('GH delivery ID', event.delivery_id)
    if event.event == "ping":
        return ""
    # Wait a bit to give Github's eventual consistency time to catch up
    await trio.sleep(1)
    gh = await g.installation_client_cache.get(
        glom(event.data, "installation.install_id"),
    )
    await router.dispatch(event, gh)
    try:
        print('GH requests remaining:', gh.rate_limit.remaining)
    except AttributeError:
        pass
    return ""

async def main():
    print("Starting up!")
    async with asks.Session(connections=100) as asks_session:
        installation_client_cache = InstallationClientCache(asks_session)
        # This is a weird way to pass arguments but I guess it works
        async with app.app_context():
            g.installation_client_cache = installation_client_cache
        async with trio.open_nursery() as nursery:
            config = hypercorn.Config.from_mapping(
                # Log to stdout
                accesslog="-",
                errorlog="-",
                # Doesn't do anything except silencing a warning:
                worker_class="trio",
            )
            url = await nursery.start(hypercorn.trio.serve, app, config)
            print("Accepting HTTP requests at:", url)

trio.run(main)
