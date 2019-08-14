import pprint
import logging
import functools

logger = logging.getLogger(__name__)

from octomachinery.app.server.runner import run as run_app
from octomachinery.app.routing import process_event_actions
from octomachinery.app.routing.decorators import process_webhook_payload
from octomachinery.app.runtime.context import RUNTIME_CONTEXT

class dotdict(dict):
    def __getattr__(self, name):
        value = self[name]
        if isinstance(value, dict):
            return dotdict(value)
        else:
            return value

def dotify_payload(fn):
    @functools.wraps(fn)
    def wrapper(event):
        return fn(event.event, dotdict(event.data))
    return wrapper

@process_event_actions('issues', {'opened'})
@process_webhook_payload
async def on_issue_opened(
        *,
        action, issue, repository, sender, installation,
        assignee=None, changes=None,
):
    """Whenever an issue is opened, greet the author and say thanks."""
    github_api = RUNTIME_CONTEXT.app_installation_client

    comments_api_url = issue["comments_url"]
    author = issue["user"]["login"]

    message = (
        f"Thanks for the report @{author}! "
        "I will look into it ASAP! (I'm a bot 🤖)."
    )
    await github_api.post(comments_api_url, data={"body": message})

@process_event_actions('issue_comment', {'created'})
@dotify_payload
async def on_issue_comment_created(event, payload):
    print(f"got a comment on {payload.issue.html_url}")
    if "pull_request" in payload.issue:
        print(f"that's a PR: {payload.issue.pull_request.html_url}")
    else:
        print("that's not a PR")
    print(f"user: {payload.comment.user.login!r}")
    print(f"body: {payload.comment.body!r}")

if __name__ == "__main__":
    print("WHEEE")
    import os
    for i in range(3):
        print(f"os.isatty({i}): {os.isatty(i)}")
    os.system(f"ls -l /proc/{os.getpid()}/fd")
    run_app(
        name='ancient-ocean-35232',
        version='1.0.0',
        url='https://github.com/apps/ancient-ocean-35232',
    )
