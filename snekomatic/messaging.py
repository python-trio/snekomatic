"""Messaging for the snekomatic app"""
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
