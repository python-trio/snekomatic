import pytest
import psycopg2
import os

# We run this test several times, and make sure that each one gets a clean
# database
@pytest.mark.parametrize("iteration", [1, 2])
def test_db_empty(heroku_style_pg, iteration):
    with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE my_table (foo int);")
            cur.execute("SELECT * FROM my_table;")
            assert cur.fetchall() == []
            cur.execute("INSERT INTO my_table (foo) VALUES (1);")
            cur.execute("SELECT * FROM my_table;")
            assert cur.fetchall() == [(1,)]
