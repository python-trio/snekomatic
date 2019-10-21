import os
import trio
import hypercorn
import hypercorn.trio
import quart
from quart import request
from quart_trio import QuartTrio

from .events import github_app

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
