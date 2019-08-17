import asks
from snekomatic.gh import BaseGithubClient, GithubApp
from gidgethub.sansio import accept_format
from glom import glom
import trio
import pendulum

TEST_USER_AGENT = "python-trio/snekomatic testing"

# These are the credentials for a real github app called "snekomatic-test",
# which is locked down to have read-only access only, on
# "njsmith-test-org/test-repo", an organization and repository that contain
# nothing of value. But it's useful for end-to-end testing of our GH API code!
TEST_APP_ID = "38758"
TEST_WEBHOOK_SECRET = "DQUSgKV8K-WnMj3TIRgzEBlnuEPe09rQ2VeKA8K7lZ4"
TEST_PRIVATE_KEY = """
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA3QWdNvdcKJAZ5Ap3Gm2YH3NmJjNyITgBpzY58ysOUabzqWBp
Zv6Ugq2JennefeEWz3x8/Cp8XEGHleuJCCRUsKCGj7lJf+fXdxZ53+RRdfYgjy5Y
P3pPOqT3ltjUZg75Msd4jNyoUwzUPpcK7N5l8XlCWKdYSfdNnmo9MWy0lrPMXU1v
3Ic0PRvdWD9+QncE64su9qgzTzGEayA1FwCX+M4dNKoX0qQWVeTcraNaZSrTTYE1
9oC/9aeMWQA87DCbtffzZzFPw8rz5L7vhtZvxpFeGQrgZ50da4MkSuxyr27Ab0wx
yLtPhVFxUUUWHzZTqhm9qVm5pIJ8f+RGL+q0aQIDAQABAoIBAQC0dFT7/9IavCyn
Z3P+++PsKcgJAI/6V0PiRf/ibhDu0aS3caQdF1Yhq5ZHjSD/HbwGA9n3+Kg4mrgc
y4XCRAdxfl7fEaTU7XGaJZu0FTH9YcsLnAcpLK9rbi1H2Bjyit8jeoEOYUp9JEhW
IfQlmR8anKpyv47yNRwGby8vH1YCg51eQPBirBNMqbP20cAW7rDk8Tz3TBiqBLsP
5rfvr+LVEMJ9y3kzZuIdFnrUUtfNEExnAeVw4f4THs7SyuFHn/iESTJWNaoNxY10
ciXj6RwQFCXzflTL1AUO5RiSvvXNBFVicSUEoHPGnuPnMruvxK/qroh0N24P9Qdc
9sSFJtNRAoGBAPgj3PR6EwgMixaUebpiO4mwwv+nGW+M0e8Bz9iUd2g9/f7U+fkN
uy2xCN5yYdsH6MII8yxbDaV6kcyMdnWRuko9KJ9zLcstylC81hB369KmwADOUl1I
BBbPeoupzsuw/6ox9/QXMO7+Ji6tCSQ1xFJyoz5Hzh9YBqIcbOGFk8XfAoGBAOQF
2m7GYv87i6nsGxWlfJF4DKsM1wIeIVMiw+ToxLEEVyxBWI13AFhAxK8paW+/qWbp
H/Ud8yMbPbLav8PIJr6cYMJSK1xN+LL0Kgq4RHaw282+mI0t6Jg2Itrr+7gfNLnG
HE4fvs+4ZYV6bPYDszAgELq7W3sIA8nrwJE3q/63AoGADQZU4sBFn3aJFnZUrWPa
nC+bDLBItYI+wrzlnAiu+9nFK0sik+AUoyFXxdVbLZQMs6KkoP9mh/kXDhWRYjpz
/NGZAEWbcb7Fj9dZpSOmTThTe7dYu2y8SjY5yHrxT9/Ki7Rzv2w4NVNBzdFnWW85
DtrVlr9OIncMYhX74RqR1yECgYAQHp3PgPTUqEf6Tjen8xf4TK1QlkrI2opujyGc
GBx3iyACf+gbsBL1Kjb9TwcmID2AifB5apGapL1a3H38ADVE+lcYxahNETIIrJwg
P+CPJ3eSduvf5yPvRrx2D4KvBH28uFWd7D6X/qgmpH35ck+DknC8Uqxn6SwjZSgq
2+2rxwKBgQDc2Xf6lJZkUNltH8yRw7WcIU0FyUAFHwMYc9IBaNudL47d9zq5/xiU
e8jTxtp/VIfaRDKa4ZM5MDAoZ/6OvKe+KwMWT8NBW6LTKc2QZRtJ6WVD1FH6kaTZ
9N78paKFQFvwHb3vXpKci0WhxYmvaUqKORJt9JuCefJcdDCk7nKk0A==
-----END RSA PRIVATE KEY-----
"""
# You can find this magic number by looking at the end of this URL:
# https://github.com/organizations/python-trio/settings/installations/1541311
# (It's also available by querying the /app/installations endpoint)
TEST_INSTALLATION_ID = "1541311"

# Smoke test for the basic asks client
async def test_basic_gh_client():
    async with asks.Session() as session:
        gh = BaseGithubClient(session, requester=TEST_USER_AGENT)
        data = await gh.getitem("/rate_limit")
        assert "rate" in data

# Some end-to-end tests for the full app's client functionality
async def test_client_part_of_app():
    app = GithubApp(
        user_agent=TEST_USER_AGENT,
        app_id=TEST_APP_ID,
        private_key=TEST_PRIVATE_KEY,
        webhook_secret=TEST_WEBHOOK_SECRET,
    )

    assert app.app_client.app is app

    # github actually won't let any app client access the /rate_limit
    # endpoint, because app credentials are so locked down. But we can look up
    # information about ourself!
    data = await app.app_client.getitem(
        "/app",
        accept=accept_format(version="machine-man-preview"),
    )
    assert glom(data, "name") == "snekomatic-test"

    # We can get an installation token
    token = await app.token_for(TEST_INSTALLATION_ID)
    # They're cached
    token2 = await app.token_for(TEST_INSTALLATION_ID)
    assert token == token2

    # And the client works too:
    i_client = app.client_for(TEST_INSTALLATION_ID)
    data = await i_client.getitem("/rate_limit")
    assert "rate" in data

    # Now we'll cheat and trick the app into thinking that the token is
    # expiring, and check that the client automatically renews it.
    soon = pendulum.now().add(seconds=10)
    app._installation_tokens[TEST_INSTALLATION_ID].expires_at = soon

    # The client still works...
    i_client = app.client_for(TEST_INSTALLATION_ID)
    data = await i_client.getitem("/rate_limit")
    assert "rate" in data

    # ...but the token has changed.
    assert token != await app.token_for(TEST_INSTALLATION_ID)

    # And let's do that again, but this time we'll have two tasks try to fetch
    # the token at the same time.
    soon = pendulum.now().add(seconds=10)
    app._installation_tokens[TEST_INSTALLATION_ID].expires_at = soon

    tokens = []

    async def get_token():
        tokens.append(await app.token_for(TEST_INSTALLATION_ID))

    async with trio.open_nursery() as nursery:
        nursery.start_soon(get_token)
        nursery.start_soon(get_token)

    # They both end up with the same token, demonstrating that they didn't do
    # two independent fetches
    assert len(tokens) == 2
    assert len(set(tokens)) == 1
