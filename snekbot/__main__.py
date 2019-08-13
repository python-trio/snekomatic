import pprint
import logging

logger = logging.getLogger(__name__)

from octomachinery.app.server.runner import run as run_app
from octomachinery.app.routing import process_event_actions
from octomachinery.app.routing.decorators import process_webhook_payload
from octomachinery.app.runtime.context import RUNTIME_CONTEXT

@process_event_actions('issues', {'opened'})
@process_webhook_payload
async def on_issue_opened(
        *,
        action, issue, repository, sender, installation,
        assignee=None, changes=None,
):
    """Whenever an issue is opened, greet the author and say thanks."""
    github_api = RUNTIME_CONTEXT.app_installation_client
    pprint.pprint(locals())
    logger.info(f"locals:\n  {pprint.pformat(locals())}")

    comments_api_url = issue["comments_url"]
    author = issue["user"]["login"]

    message = (
        f"Thanks for the report @{author}! "
        "I will look into it ASAP! (I'm a bot 🤖)."
    )
    await github_api.post(comments_api_url, data={"body": message})

if __name__ == "__main__":
    run_app(
        name='ancient-ocean-35232',
        version='1.0.0',
        url='https://github.com/apps/ancient-ocean-35232',
    )
