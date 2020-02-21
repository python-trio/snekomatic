import os
from pathlib import Path
from sqlalchemy import create_engine, MetaData, Table, Column, String
from sqlalchemy.sql.expression import select, exists
import alembic.config
import alembic.command
import alembic.migration
import alembic.autogenerate
import pprint
import attr

metadata = MetaData()

sent_invitation = Table(
    "persistent_set_sent_invitation",
    metadata,
    Column("entry", String, primary_key=True),
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

        # Run any necessary migrations
        with engine.connect() as conn:
            alembic_cfg = alembic.config.Config(
                Path(__file__).parent / "alembic.ini"
            )
            alembic_cfg.attributes["connection"] = conn
            alembic.command.upgrade(alembic_cfg, "head")

        # Verify that the actual final schema matches what we expect
        with engine.connect() as conn:
            mc = alembic.migration.MigrationContext.configure(conn)
            diff = alembic.autogenerate.compare_metadata(mc, metadata)
            if diff:
                print("!!! mismatch between db schema and code")
                pprint.pprint(diff)
                raise RuntimeError("consistency check failed")

        # Iff that all worked out, then save the engine so we can skip those
        # checks next time
        CACHED_ENGINE = CachedEngine(engine, os.environ["DATABASE_URL"])
    return CACHED_ENGINE.engine.connect()


class SentInvitation:
    @staticmethod
    def contains(name):
        with get_conn() as conn:
            # This is:
            #   SELECT EXISTS (SELECT 1 FROM sent_invitation WHERE entry = ?)
            return conn.execute(
                select(
                    [
                        exists(
                            select([1]).where(sent_invitation.c.entry == name)
                        )
                    ]
                )
            ).scalar()

    @staticmethod
    def add(name):
        with get_conn() as conn:
            conn.execute(sent_invitation.insert(), entry=name)
