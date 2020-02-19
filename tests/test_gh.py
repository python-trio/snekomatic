import pytest

import asks
import attr
from snekomatic.gh import (
    BaseGithubClient,
    GithubApp,
    reply_url,
    reaction_url,
    get_comment_body,
)
import gidgethub
from gidgethub.sansio import accept_format
from glom import glom
import trio
import pendulum
import os
import json
from pathlib import Path

from .util import fake_webhook, save_environ
from .credentials import *

SAMPLE_DATA_DIR = Path(__file__).absolute().parent / "sample-data"


def get_sample_data(name):
    data = json.loads((SAMPLE_DATA_DIR / (name + ".json")).read_text())
    data["installation"]["id"] = TEST_INSTALLATION_ID
    return data


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


def test_app_envvar_fallback():
    with save_environ():
        os.environ["GITHUB_USER_AGENT"] = TEST_USER_AGENT
        os.environ["GITHUB_APP_ID"] = TEST_APP_ID
        os.environ["GITHUB_PRIVATE_KEY"] = TEST_PRIVATE_KEY
        os.environ["GITHUB_WEBHOOK_SECRET"] = TEST_WEBHOOK_SECRET

        app = GithubApp()
        assert app.app_id == TEST_APP_ID
        assert app.user_agent == TEST_USER_AGENT
        assert app.private_key == TEST_PRIVATE_KEY
        assert app.webhook_secret == TEST_WEBHOOK_SECRET


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

    # Missing secret
    with pytest.raises(gidgethub.ValidationFailure):
        await app.dispatch_webhook(
            *fake_webhook(
                "pull_request",
                {"action": "created", "installation": {"id": "xyzzy"}},
                secret=None,
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


async def test_github_app_webhook_client_works():
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


@attr.s
class WebhookScenario(object):
    test_data = attr.ib()
    event_type = attr.ib()
    expected_body = attr.ib()
    expected_reply_url = attr.ib()
    expected_reaction_url = attr.ib()
    def payload(self):
        return get_sample_data(self.test_data)
    def body(self):
        return get_comment_body(self.event_type, self.payload())
    def reply_url(self):
        return reply_url(self.event_type, self.payload())
    def reaction_url(self):
        return reaction_url(self.event_type, self.payload())


# FIXME: other comment types
webhook_scenarios = [
    WebhookScenario(test_data="issue-created-webhook",
             event_type="issues",
             expected_body="This must be addressed immediately, if not before.",
             expected_reply_url="https://api.github.com/repos/njsmith-test-org/test-repo/issues/5/comments",
             expected_reaction_url="https://api.github.com/repos/njsmith-test-org/test-repo/issues/5/reactions",
             ),
    WebhookScenario(test_data="comment-existing-issue",
             event_type="issue_comment",
             expected_body="I agree with the original poster.",
             expected_reply_url="https://api.github.com/repos/njsmith-test-org/test-repo/issues/5/comments",
             expected_reaction_url="https://api.github.com/repos/njsmith-test-org/test-repo/issues/comments/544211719/reactions",
             ),
    WebhookScenario(test_data="comment-edited",
             event_type="issue_comment",
             expected_body="I agree with the original poster.\r\n\r\n[EDIT: on further thought, I disagree.]",
             expected_reply_url="https://api.github.com/repos/njsmith-test-org/test-repo/issues/5/comments",
             expected_reaction_url="https://api.github.com/repos/njsmith-test-org/test-repo/issues/comments/544211719/reactions",
             ),
    WebhookScenario(test_data="new-pr-created",
             event_type="pull_request",
             expected_body="",
             expected_reply_url="https://api.github.com/repos/njsmith-test-org/test-repo/issues/6/comments",
             expected_reaction_url="https://api.github.com/repos/njsmith-test-org/test-repo/issues/6/reactions",
             ),
    WebhookScenario(test_data="comment-existing-pr",
             event_type="issue_comment",
             expected_body="hello world :wave: ",
             expected_reply_url="https://api.github.com/repos/njsmith-test-org/test-repo/issues/6/comments",
             expected_reaction_url="https://api.github.com/repos/njsmith-test-org/test-repo/issues/comments/544211921/reactions",
             ),
    WebhookScenario(test_data="add-single-comment",
             event_type="pull_request_review",
             expected_body="",
             expected_reply_url="https://api.github.com/repos/njsmith-test-org/test-repo/issues/6/comments",
             expected_reaction_url="https://api.github.com/repos/njsmith-test-org/test-repo/pulls/6/reviews/304238138/reactions",
             ),
    WebhookScenario(test_data="pr-review-comment",
             event_type="pull_request_review_comment",
             expected_body="This is just a standalone comment.",
             expected_reply_url="https://api.github.com/repos/njsmith-test-org/test-repo/pulls/6/comments/336759908/replies",
             expected_reaction_url="https://api.github.com/repos/njsmith-test-org/test-repo/pulls/comments/336759908/reactions",
             ),
    WebhookScenario(test_data="full-pr-review",
             event_type="pull_request_review",
             expected_body="Truly a critical fix. However, maybe it needs more cowbell?",
             expected_reply_url="https://api.github.com/repos/njsmith-test-org/test-repo/issues/6/comments",
             expected_reaction_url="https://api.github.com/repos/njsmith-test-org/test-repo/pulls/6/reviews/304238151/reactions",
             ),
    WebhookScenario(test_data="pr-review-comment-01",
             event_type="pull_request_review_comment",
             expected_body="This is part of a review.",
             expected_reply_url="https://api.github.com/repos/njsmith-test-org/test-repo/pulls/6/comments/336759921/replies",
             expected_reaction_url="https://api.github.com/repos/njsmith-test-org/test-repo/pulls/comments/336759921/reactions",
             ),
    WebhookScenario(test_data="pr-review",
             event_type="pull_request_review",
             expected_body="Truly a critical fix. However, maybe it needs more cowbell?",
             expected_reply_url="https://api.github.com/repos/njsmith-test-org/test-repo/issues/6/comments",
             expected_reaction_url="https://api.github.com/repos/njsmith-test-org/test-repo/pulls/6/reviews/304238151/reactions",
             ),
]


@pytest.mark.parametrize("scenario", webhook_scenarios)
def test_webhook_scenarios(scenario):
    assert scenario.body() == scenario.expected_body
    assert scenario.reply_url() == scenario.expected_reply_url
    assert scenario.reaction_url() == scenario.expected_reaction_url


@attr.s
class CommandScenario:
    body = attr.ib()
    expected_commands = attr.ib()

command_scenarios = [
    CommandScenario(
        body="/test-command hi",
        expected_commands=[["/test-command", "hi"]],
    ),
    CommandScenario(
        body="Looks good!\n/test-command\n\n\n  /test-command   hello  ",
        expected_commands=[["/test-command"], ["/test-command", "hello"]],
    ),
    CommandScenario(
        body=None,
        expected_commands=[],
    ),
]

@pytest.mark.parametrize("scenario", command_scenarios)
async def test_github_app_command_routing(autojump_clock, scenario):
    app = GithubApp(
        user_agent=TEST_USER_AGENT,
        app_id=TEST_APP_ID,
        private_key=TEST_PRIVATE_KEY,
        webhook_secret=TEST_WEBHOOK_SECRET,
    )

    test_payload = get_sample_data("issue-created-webhook")
    test_payload["issue"]["body"] = scenario.body

    got_commands = []

    @app.route_command("test-command")
    async def test_command_handler(command, event_type, payload, gh_client):
        assert gh_client.installation_id == TEST_INSTALLATION_ID
        assert event_type == "issues"
        assert payload == test_payload
        got_commands.append(command)

    await app.dispatch_webhook(
        *fake_webhook("issues", test_payload, secret=TEST_WEBHOOK_SECRET)
    )

    assert got_commands == scenario.expected_commands
