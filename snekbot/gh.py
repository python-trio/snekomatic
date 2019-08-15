import asks
from collections import defaultdict
import trio  # XX switch to anyio here?
from gidgethub.sansio import Event, accept_format
import gidgethub.abc
import pendulum
import jwt
import attrs

# XX TODO: add caching

# Assume that there might be this much offset between our clock at the time of
# submitting a request and Github's clock at the time of processing the
# request, or vice-versa.
MAX_CLOCK_SKEW = pendulum.Duration(minutes=1)

def _too_close_for_comfort(expiration_datetime):
    return pendulum.now() + MAX_CLOCK_SKEW > expiration_datetime

class BaseGithubClient(gidgethub.abc.GithubAPI):
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
        # asks stores headers in a regular dict. They're probably lowercase
        # already, but let's be 100% certain.
        lower_headers = {
            key.lower(): value for (key, value) in response.headers.items()
        }
        return response.status_code, lower_headers, await response.read()

    # Why does gidgethub make this mandatory? it's not used for anything
    async def sleep(self, seconds):
        await trio.sleep(seconds)


class AppGithubClient(BaseGithubClient):
    def __init__(self, *, app):
        self._app = app
        super().__init__(app._session, requestor=app.user_agent)

    async def _make_request(self, *args, **kwargs):
        now = pendulum.now()
        jwt_app_token = jwt.encode(
            {
                "iat": (now - MAX_CLOCK_SKEW).int_timestamp,
                "exp": (now + MAX_CLOCK_SKEW).int_timestamp,
                "iss": self._app.app_id,
            },
            key=self._private_key,
            algorithm="RS256",
        )
        kwargs["oauth_token"] = None
        kwargs["jwt"] = jwt_app_token
        return await super()._make_request(*args, **kwargs)


class InstallationGithubClient(BaseGithubClient):
    def __init__(self, *, app, installation_id):
        self._app = app
        self._installation_id = installation_id
        super().__init__(app._session, requestor=app.user_agent)

    async def _make_request(self, *args, **kwargs):
        token = await self._app._get_token(self._installation_id)
        kwargs["oauth_token"] = token
        kwargs["jwt"] = None
        return await super()._make_request(*args, **kwargs)


def _env_fallback(name, passed):
    if passed is not None:
        return passed
    envvar_name = f"GITHUB_{name.upper()}"
    if envvar_name not in os.environ:
        raise RuntimeError(
            f"you must either pass {name}= or set {envvar_name}"
        )
    return os.environ[envvar_name]


@attr.s
class CachedInstallationToken:
    token = attr.ib(default="")
    # pendulum.DateTime
    expires_at = attr.ib(default=pendulum.DateTime(1900, 1, 1))
    # if a refresh is already in progress, a trio.Event
    # otherwise, None
    refresh_event = attr.ib(default=None)


class GithubApp:
    def __init__(
            self,
            *,
            session=None,
            app_id=None,
            user_agent=None,
            private_key=None,
            webhook_secret=None,
    ):
        if session is None:
            session = asks.Session(connections=999)
        self._session = session
        self.app_id = _env_fallback("app_id", app_id)
        self.user_agent = _env_fallback("user_agent", user_agent)
        self._private_key = _env_fallback("private_key", private_key)
        self._webhook_secret = _env_fallback("webhook_secret", webhook_secret)
        self._installation_tokens = defaultdict(CachedInstallationToken)

        self.app_client = AppGithubClient(self)

    def client_for(self, installation_id):
        return InstallationGithubClient(self, installation_id)

    async def _get_token(self, installation_id):
        cit = self._installation_tokens[installation_id]

        while _too_close_for_comfort(cit.expires_at):
            print(f"{installation_id}: Token is expiring soon")
            if cit.refresh_event is not None:
                print(f"{installation_id}: Renewal already in progress; waiting")
                await cit.refresh_event.wait()
            else:
                print(f"{installation_id}: Renewing now")
                try:
                    cit.refresh_event = trio.Event()
                    response = await self.app_client.post(
                        "/app/installations{/installation_id}/access_tokens",
                        url_vars={"installation_id": installation_id},
                        accept=accept_format(version="machine-man-preview"),
                    )
                    cit.token = response["token"]
                    cit.expires_at = pendulum.parse(response["expires_at"])
                    assert not _too_close_for_comfort(cit.expires_at)
                    print(f"{installation_id}: Renewed successfully")
                finally:
                    # Make sure that even if we get cancelled, any other tasks
                    # will still wake up (and can retry the operation)
                    cit.refresh_event.set()
                    cit.refresh_event = None

        return cit.token
