# TODO:
# - send it a webhook and observe what it does...
#   for this, should fake out github client api with canned responses
#   and make assertions about what they do
#   - in database
#   - not in database, but in member list
#   - not in either -> sends invitation!

# easiest way is probably to monkeypatch BaseGithubClient._request

import pytest
import os
import asks

from snekomatic.app import main
from .util import fake_webhook, save_environ
from .credentials import *


@pytest.fixture
async def our_app_url(nursery, heroku_style_pg):
    with save_environ():
        os.environ["GITHUB_USER_AGENT"] = TEST_USER_AGENT
        os.environ["GITHUB_APP_ID"] = TEST_APP_ID
        os.environ["GITHUB_PRIVATE_KEY"] = TEST_PRIVATE_KEY
        os.environ["GITHUB_WEBHOOK_SECRET"] = TEST_WEBHOOK_SECRET
        os.environ["PORT"] = "0"  # let the OS pick an unused port

        urls = await nursery.start(main)
        yield urls[0]


async def test_main_smoke(our_app_url):
    response = await asks.get(our_app_url)
    assert "Hi!" in response.text
