# Make sure that print's are flushed immediately so heroku's logging
# infrastructure can see them.
import sys
sys.stdout.reconfigure(line_buffering=True)

import os
import trio
from glom import glom
import asks
import hypercorn
import hypercorn.trio
import quart
from quart import request, g
from quart_trio import QuartTrio

from .gh import GithubApp

# we should stash the delivery id in a contextvar and include it in logging
# also maybe structlog? eh print is so handy for now

quart_app = QuartTrio("snekbot")
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

@quart_app.route("/oops")
async def oops():
    raise RuntimeError("roh uh")

@quart_app.route("/webhook/github", methods=["POST"])
async def webhook_github():
    body = await request.get_data()
    await github_app.dispatch_webhook(request.headers, body)
    return ""

@github_app.route("issues", action="opened")
async def on_issue_opened(gh_client, event_type, payload):
    print("New issue was created")
    comments_api_url = glom(payload, "issue.comments_url")
    author = glom(payload, "issue.user.login")
    message = (
        f"Thanks for the report @{author}! "
        "I will look into it ASAP! (I'm a bot 🤖)."
    )
    await gh_client.post(comments_api_url, data={"body": message})

async def main():
    print("Starting up!")
    # On Heroku, have to bind to whatever $PORT says:
    # https://devcenter.heroku.com/articles/dynos#local-environment-variables
    port = os.environ.get("PORT", 8000)
    async with trio.open_nursery() as nursery:
        config = hypercorn.Config.from_mapping(
            bind=["127.0.0.1:{port}"],
            # Log to stdout
            accesslog="-",
            errorlog="-",
            # Setting this just silences a warning:
            worker_class="trio",
        )
        url = await nursery.start(hypercorn.trio.serve, quart_app, config)
        print("Accepting HTTP requests at:", url)

trio.run(main)
