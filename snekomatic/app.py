import sys
import os
import trio
from glom import glom
import hypercorn
import hypercorn.trio
import quart
from quart import request
from quart_trio import QuartTrio
import gidgethub
from gidgethub.sansio import accept_format

from .db import SentInvitation
from .gh import GithubApp, reply_url, reaction_url

# we should stash the delivery id in a contextvar and include it in logging
# also maybe structlog? eh print is so handy for now

# Maybe:
# send message on first PR, with basic background info – volunteer project,
# super appreciate their contribution, also means we're sometimes slow.
# how to ping?
#
# send message with invitation giving info
#
# after they accept, post a closed issue to welcome them, and invite them to
# ask any questions and introduce themselves there? and also highlight it in
# the chat? (include link to search for their contributions, as part of the
# introduction?)
#
# in the future would be nice if bot could do some pings, both ways
#
# include some specific suggestions on how to get help? assign a mentor from a
# list of volunteers?
#
# I almost wonder if it would be better to give membership on like, the 3rd
# merged PR
# with the bot keeping track, and posting an encouraging countdown on each
# merged PR, so it feels more like an incremental process, where you can see
# the milestone coming and then when you get there it *is* a milestone.

quart_app = QuartTrio(__name__)
github_app = GithubApp()

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


@quart_app.route("/")
async def index():
    return "Hi! 🐍🐍🐍"


@quart_app.route("/webhook/github", methods=["POST"])
async def webhook_github():
    body = await request.get_data()
    await github_app.dispatch_webhook(request.headers, body)
    return ""


# dedent, remove single newlines (but not double-newlines), remove
# leading/trailing newlines
def _fix_markdown(s):
    import textwrap

    s = s.strip("\n")
    s = textwrap.dedent(s)
    s = s.replace("\n\n", "__PARAGRAPH_BREAK__")
    s = s.replace("\n", " ")
    s = s.replace("__PARAGRAPH_BREAK__", "\n\n")
    return s


invite_message = _fix_markdown(
    """
    Hey @{username}, it looks like that was the first time we merged one of
    your PRs! Thanks so much! :tada: :birthday:

    If you want to keep contributing, we'd love to have you. So, I just sent
    you an invitation to join the python-trio organization on Github! If you
    accept, then here's what will happen:

    * Github will automatically subscribe you to notifications on all our
      repositories. (But you can unsubscribe again if you don't want the
      spam.)

    * You'll be able to help us manage issues (add labels, close them, etc.)

    * You'll be able to review and merge other people's pull requests

    * You'll get a [member] badge next to your name when participating in the
      Trio repos, and you'll have the option of adding your name to our
      [member's page](https://github.com/orgs/python-trio/people) and putting
      our icon on your Github profile
      ([details](https://help.github.com/en/articles/publicizing-or-hiding-organization-membership))

    If you want to read more, [here's the relevant section in our contributing
    guide](https://trio.readthedocs.io/en/latest/contributing.html#joining-the-team).

    Alternatively, you're free to decline or ignore the invitation. You'll
    still be able to contribute as much or as little as you like, and I won't
    hassle you about joining again. But if you ever change your mind, just let
    us know and we'll send another invitation. We'd love to have you, but more
    importantly we want you to do whatever's best for you.

    If you have any questions, well... I am just a [humble Python
    script](https://github.com/python-trio/snekomatic), so I probably can't
    help. But please do post a comment here, or [in our
    chat](https://gitter.im/python-trio/general), or [on our
    forum](https://trio.discourse.group/c/help-and-advice), whatever's
    easiest, and someone will help you out!

    """
)


async def _member_state(gh_client, org, member):
    # Returns "active" (they're a member), "pending" (they're not a member,
    # but they have an invitation they haven't responded to yet), or None
    # (they're not a member and don't have a pending invitation)
    try:
        response = await gh_client.getitem(
            "/orgs/{org}/memberships/{username}",
            url_vars={"org": org, "username": member},
        )
    except gidgethub.BadRequest as exc:
        if exc.status_code == 404:
            return None
        else:
            raise
    else:
        return glom(response, "state")


# There's no "merged" event; instead you get action=closed + merged=True
@github_app.route("pull_request", action="closed")
async def pull_request_merged(event_type, payload, gh_client):
    print("PR closed")
    if not glom(payload, "pull_request.merged"):
        print("but not merged, so never mind")
        return
    creator = glom(payload, "pull_request.user.login")
    org = glom(payload, "organization.login")
    print(f"PR by {creator} was merged!")

    if SentInvitation.contains(creator):
        print("The database says we already sent an invitation")
        return

    state = await _member_state(gh_client, org, creator)
    if state is not None:
        # Remember for later so we don't keep checking the Github API over and
        # over.
        SentInvitation.add(creator)
        print(f"They already have member state {state}; not inviting")
        return

    print("Inviting! Woohoo!")
    # Send an invitation
    await gh_client.put(
        "/orgs/{org}/memberships/{username}",
        url_vars={"org": org, "username": creator},
        data={"role": "member"},
    )
    # Record that we did
    SentInvitation.add(creator)
    # Welcome them
    await gh_client.post(
        glom(payload, "pull_request.comments_url"),
        data={"body": invite_message.format(username=creator)},
    )


@github_app.route_command("ping")
async def handle_ping(command, event_type, payload, gh_client):
    assert command == ["ping"]
    await gh_client.post(
        reply_url(event_type, payload), data={"body": "pong!"}
    )
    await gh_client.post(
        reaction_url(event_type, payload),
        data={"content": "heart"},
        accept=accept_format(version="squirrel-girl-preview"),
    )


async def main(*, task_status=trio.TASK_STATUS_IGNORED):
    print("~~~ Starting up! ~~~")
    # On Heroku, have to bind to whatever $PORT says:
    # https://devcenter.heroku.com/articles/dynos#local-environment-variables
    port = os.environ.get("PORT", 8000)
    async with trio.open_nursery() as nursery:
        config = hypercorn.Config.from_mapping(
            bind=[f"0.0.0.0:{port}"],
            # Log to stdout
            accesslog="-",
            errorlog="-",
            # Setting this just silences a warning:
            worker_class="trio",
        )
        urls = await nursery.start(hypercorn.trio.serve, quart_app, config)
        print("Accepting HTTP requests at:", urls)
        task_status.started(urls)
