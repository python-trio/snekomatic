import pytest

import asks
from snekomatic.gh import BaseGithubClient, GithubApp
import gidgethub
from gidgethub.sansio import accept_format
from glom import glom
import trio
import pendulum
import os

from .util import fake_webhook, save_environ
from .credentials import *

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
        "/app", accept=accept_format(version="machine-man-preview")
    )
    assert glom(data, "name") == "snekomatic-test"

    # We can get an installation token
    token = await app.token_for(TEST_INSTALLATION_ID)
    # They're cached
    token2 = await app.token_for(TEST_INSTALLATION_ID)
    assert token == token2

    # And the client works too:
    i_client = app.client_for(TEST_INSTALLATION_ID)
    assert i_client.app is app
    assert i_client.installation_id == TEST_INSTALLATION_ID
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


def test_app_init_envvar_fallback():
    with save_environ():
        os.environ["GITHUB_USER_AGENT"] = TEST_USER_AGENT
        os.environ["GITHUB_APP_ID"] = TEST_APP_ID
        os.environ["GITHUB_PRIVATE_KEY"] = TEST_PRIVATE_KEY
        os.environ["GITHUB_WEBHOOK_SECRET"] = TEST_WEBHOOK_SECRET

        app = GithubApp()
        assert app.app_id == TEST_APP_ID
        assert app.user_agent == TEST_USER_AGENT
        assert app._private_key == TEST_PRIVATE_KEY
        assert app._webhook_secret == TEST_WEBHOOK_SECRET

    with pytest.raises(RuntimeError):
        GithubApp()


async def test_github_app_webhook_routing(autojump_clock):
    app = GithubApp(
        user_agent=TEST_USER_AGENT,
        app_id=TEST_APP_ID,
        private_key=TEST_PRIVATE_KEY,
        webhook_secret=TEST_WEBHOOK_SECRET,
    )

    record = []

    @app.route("pull_request")
    async def pull_request_any(event_type, payload, client):
        record.append(("pull_request_all", event_type, payload, client))

    @app.route("pull_request", action="created")
    async def pull_request_created(event_type, payload, client):
        record.append(("pull_request_created", event_type, payload, client))

    async def issue_created(event_type, payload, client):
        record.append(("issue_created", event_type, payload, client))

    app.add(issue_created, "issue", action="created")

    with pytest.raises(TypeError):

        @app.route("pull_request", action="created", user="njsmith")
        async def unnused(event_type, payload, client):  # pragma: no cover
            pass

    ################################################################

    await app.dispatch_webhook(
        *fake_webhook(
            "pull_request",
            {
                "action": "created",
                "installation": {"id": TEST_INSTALLATION_ID},
            },
            secret=TEST_WEBHOOK_SECRET,
        )
    )

    assert set(r[0] for r in record) == {
        "pull_request_all",
        "pull_request_created",
    }
    _, received_event_type, received_payload, received_client = record[0]
    assert received_event_type == "pull_request"
    assert received_payload["action"] == "created"
    assert received_client.installation_id == TEST_INSTALLATION_ID

    record.clear()

    ################################################################

    await app.dispatch_webhook(
        *fake_webhook(
            "issue",
            {"action": "created", "installation": {"id": "xyzzy"}},
            secret=TEST_WEBHOOK_SECRET,
        )
    )

    assert len(record) == 1
    receiver, received_event_type, received_payload, received_client = record[
        0
    ]
    assert receiver == "issue_created"
    assert received_event_type == "issue"
    assert received_client.installation_id == "xyzzy"

    record.clear()

    ################################################################

    # No action= field
    await app.dispatch_webhook(
        *fake_webhook(
            "pull_request",
            {"installation": {"id": "xyzzy"}},
            secret=TEST_WEBHOOK_SECRET,
        )
    )

    assert len(record) == 1
    assert record[0][0] == "pull_request_all"

    record.clear()

    ################################################################

    # Wrong secret
    with pytest.raises(gidgethub.ValidationFailure):
        await app.dispatch_webhook(
            *fake_webhook(
                "pull_request",
                {"action": "created", "installation": {"id": "xyzzy"}},
                secret="trust me",
            )
        )

    assert not record

    record.clear()

    ################################################################

    # No installation id
    await app.dispatch_webhook(
        *fake_webhook("ping", {}, secret=TEST_WEBHOOK_SECRET)
    )

    assert not record

    record.clear()


async def test_github_app_webhook_client_works(autojump_clock):
    app = GithubApp(
        user_agent=TEST_USER_AGENT,
        app_id=TEST_APP_ID,
        private_key=TEST_PRIVATE_KEY,
        webhook_secret=TEST_WEBHOOK_SECRET,
    )

    handler_ran = False

    @app.route("pull_request")
    async def handler(event_type, payload, client):
        nonlocal handler_ran
        handler_ran = True
        assert "rate" in await client.getitem("/rate_limit")

    await app.dispatch_webhook(
        *fake_webhook(
            "pull_request",
            {
                "action": "created",
                "installation": {"id": TEST_INSTALLATION_ID},
            },
            secret=TEST_WEBHOOK_SECRET,
        )
    )

    assert handler_ran
