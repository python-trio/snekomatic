import pytest
import psycopg2
import os
import random

# Enable pytest-trio's "trio mode"
from pytest_trio.enable_trio_mode import *

# Fixture that sets up an empty postgres db and sets $DATABASE_URL to point to
# it, then tears it down afterwards.
#
# Assumes that there's a password-less postgres running on localhost on the
# default port. For example:
#
#   docker run --rm -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust postgres:alpine

BASE_DATABASE_URL = "postgresql://postgres@localhost"


@pytest.fixture
def heroku_style_pg():
    test_db_name = "".join(
        random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(10)
    )
    with psycopg2.connect(BASE_DATABASE_URL) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE {test_db_name};")
    os.environ["DATABASE_URL"] = f"{BASE_DATABASE_URL}/{test_db_name}"
    yield
    del os.environ["DATABASE_URL"]
    with psycopg2.connect(BASE_DATABASE_URL) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            # Kill any existing connections (can't drop a db with existing
            # connections)
            cur.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s;
                """,
                (test_db_name,),
            )
            cur.execute(f"DROP DATABASE {test_db_name};")
