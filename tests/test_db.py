from snekomatic.db import SentInvitation


def test_SentInvitation(heroku_style_pg):
    assert not SentInvitation.contains("foo")
    assert not SentInvitation.contains("bar")
    SentInvitation.add("foo")
    assert SentInvitation.contains("foo")
    assert not SentInvitation.contains("bar")
