import os
import psycopg2

class PersistentStringSet:
    def __init__(self, name):
        self._table_name = f"persistent_set_{name}"

    def _conn(self):
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cursor = conn.cursor()
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._table_name} (
                entry  text PRIMARY KEY
            );
            """
        )
        conn.commit()
        return conn

    def __contains__(self, value):
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT exists
                   (SELECT 1 FROM {self._table_name} WHERE entry = %s);
                """,
                (value,),
            )
            (exists,) = cursor.fetchone()
            return exists

    def add(self, value):
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                INSERT INTO {self._table_name} (entry) VALUES (%s);
                """,
                (value,),
            )
            conn.commit()
