import os
import psycopg2
import pytest
from snekomatic.db import SentInvitation


def test_SentInvitation(heroku_style_pg):
    assert not SentInvitation.contains("foo")
    assert not SentInvitation.contains("bar")
    SentInvitation.add("foo")
    assert SentInvitation.contains("foo")
    assert not SentInvitation.contains("bar")


def test_consistency_check(heroku_style_pg):
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE unexpected_table_asdofhsdf (hi integer);")

    # Now any attempt to access the database should raise an exception
    with pytest.raises(RuntimeError):
        SentInvitation.contains("foo")
    with pytest.raises(RuntimeError):
        SentInvitation.add("foo")
