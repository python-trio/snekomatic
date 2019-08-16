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
import psycopg2

from .gh import GithubApp

# we should stash the delivery id in a contextvar and include it in logging
# also maybe structlog? eh print is so handy for now

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
# leading/trailing whitespace (around the whole message)
def _fix_markdown(s):
    import textwrap
    s = s.strip()
    s = textwrap.dedent(s)
    s = s.replace("\n\n", "__PARAGRAPH_BREAK__")
    s = s.replace("\n", " ")
    s = s.replace("__PARAGRAPH_BREAK__", "\n\n")
    return s

class PersistentStringSet:
    def __init__(self, name):
        self._table_name = f"persistent_set_{name}"

    def _conn(self):
        conn = psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require")
        cursor = conn.cursor()
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._table_name} (
                entry  text PRIMARY KEY
            );
            """
        )
        conn.commit()
        return conn

    def __contains__(self, value):
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT exists
                   (SELECT 1 FROM {self._table_name} WHERE entry = %s);
                """,
                (value,),
            )
            got = cursor.fetchone()
            print(got)
            return got[0]

    def add(self, value):
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                INSERT INTO {self._table_name} (entry) VALUES (%s);
                """,
                (value,),
            )
            conn.commit()


SENT_INVITATION = PersistentStringSet("SENT_INVITATION")


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

    * You'll get a [member] badge next to your name when posting here, and
      you'll have the option of adding your name to our [member's
      page](https://github.com/orgs/python-trio/people) and putting our icon
      on your Github profile
      ([details](https://help.github.com/en/articles/publicizing-or-hiding-organization-membership))

    If you want to read more, [here's the relevant section in our contributing
    guide](https://trio.readthedocs.io/en/latest/contributing.html#joining-the-team).

    If you decline, then you can still submit PRs, but I won't hassle you
    again. And if you ever change your mind, just let us know, and we'll send
    another invitation. Or, you can ignore the invitation entirely, and it'll
    still be there for you later. You should do whatever's best for you!

    If you have any questions, well... I am just a humble Python script, so I
    probably can't help. But feel free to post a comment here, or [in our
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
    merger = glom(payload, "pull_request.merged_by.login")
    org = glom(payload, "organization.login")
    print(f"PR by {creator} was merged by {merger}!")

    if creator in SENT_INVITATION:
        print("The database says we already sent an invitation")
        return

    state = await _member_state(gh_client, org, creator)
    if state is not None:
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
    SENT_INVITATION.add(creator)
    # Welcome them
    await gh_client.post(
        glom(payload, "pull_request.comments_url"),
        data={"body": invite_message.format(username=creator)},
    )


async def main():
    # Make sure that print's are flushed immediately so heroku's logging
    # infrastructure can see them.
    sys.stdout.reconfigure(line_buffering=True)

    print("~~~ Starting up! ~~~")

    # Check if the set works at all
    import secrets
    fake_name = secrets.token_hex(5)
    print(f"{fake_name} in set: {fake_name in SENT_INVITATION}")
    SENT_INVITATION.add(fake_name)
    print(f"{fake_name} in set: {fake_name in SENT_INVITATION}")

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
        url = await nursery.start(hypercorn.trio.serve, quart_app, config)
        print("Accepting HTTP requests at:", url)


trio.run(main)
