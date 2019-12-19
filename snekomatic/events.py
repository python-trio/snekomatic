"""Github Event handlers for the snekomatic app."""
import gidgethub
from glom import glom
from .gh import GithubApp
from .db import PersistentStringSet
from .messaging import invite_message


github_app = GithubApp()
SENT_INVITATION = PersistentStringSet("SENT_INVITATION")


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

    if creator in SENT_INVITATION:
        print("The database says we already sent an invitation")
        return

    state = await _member_state(gh_client, org, creator)
    if state is not None:
        # Remember for later so we don't keep checking the Github API over and
        # over.
        SENT_INVITATION.add(creator)
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
