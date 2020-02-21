import os
from sqlalchemy import create_engine, MetaData, Table, Column, String
from sqlalchemy.sql.expression import select, exists
import attr

metadata = MetaData()

sent_invitation = Table(
    "sent_invitation", metadata, Column("entry", String, primary_key=True)
)

@attr.s
class CachedEngine:
    engine = attr.ib()
    database_url = attr.ib()

CACHED_ENGINE = CachedEngine(None, None)

def get_conn():
    global CACHED_ENGINE
    if CACHED_ENGINE.database_url != os.environ["DATABASE_URL"]:
        engine = create_engine(os.environ["DATABASE_URL"])
        CACHED_ENGINE = CachedEngine(engine, os.environ["DATABASE_URL"])
        metadata.create_all(engine)
    return CACHED_ENGINE.engine.connect()


class SentInvitation:
    @staticmethod
    def contains(name):
        with get_conn() as conn:
            # This is:
            #   SELECT EXISTS (SELECT 1 FROM sent_invitation WHERE entry = ?)
            return conn.execute(
                select(
                    [exists(select([1]).where(sent_invitation.c.entry == name))]
                )
            ).scalar()

    @staticmethod
    def add(name):
        with get_conn() as conn:
            conn.execute(sent_invitation.insert(), entry=name)
