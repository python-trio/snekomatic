"""empty message

Revision ID: 1479437ee1e2
Revises: 
Create Date: 2020-02-21 12:03:25.898594

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1479437ee1e2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "persistent_set_sent_invitation",
        sa.Column("entry", sa.String, primary_key=True),
    )


def downgrade():
    op.drop_table("persistent_set_sent_invitation")
