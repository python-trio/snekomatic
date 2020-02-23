import os
from sqlalchemy import create_engine
from sqlalchemy import pool

from alembic import context

from snekomatic.db import metadata

try:
    connection = context.config.attributes["connection"]
except KeyError:
    engine = create_engine(os.environ["DATABASE_URL"])
    connection = engine.connect()

context.configure(connection=connection, target_metadata=metadata)
with context.begin_transaction():
    context.run_migrations()
