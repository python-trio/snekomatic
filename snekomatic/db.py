import os
from sqlalchemy import create_engine, MetaData, Table, Column, String
from sqlalchemy.sql.expression import select, exists
import psycopg2

metadata = MetaData()

sent_invitation = Table(
    "sent_invitation", metadata, Column("entry", String, primary_key=True)
)


def get_conn():
    # XX TODO: maybe cache the engine and recreate it iff DATABASE_URL
    # changes? (and run alembic automatically at that point)
    engine = create_engine(os.environ["DATABASE_URL"])
    metadata.create_all(engine)
    return engine.connect()


class SentInvitation:
    @staticmethod
    def contains(name):
        with get_conn() as conn:
            # This is basically:
            #   SELECT EXISTS (SELECT 1 FROM sent_invitation WHERE entry = <name>)
            return conn.execute(
                select(
                    [exists(select([1]).where(sent_invitation.c.entry == name))]
                )
            ).scalar()

    @staticmethod
    def add(name):
        with get_conn() as conn:
            conn.execute(sent_invitation.insert(), entry=name)
