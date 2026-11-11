"""The place names of the owner (#2215, epic #2214): the new table `place_names`.

Revision ID: 0054
Revises: 0053

No data loss: the upgrade adds the new table `place_names`. The downgrade drops only this new table, so the
place names that the owner stored are lost.
"""

import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "place_names",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("city", sa.String(60), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("place_names")
