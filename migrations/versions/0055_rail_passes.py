"""The rail passes of the owner (#2265): the new table `rail_passes`.

Revision ID: 0055
Revises: 0054

No data loss: the upgrade adds the new table `rail_passes`. The downgrade drops only this new table, so the
rail passes that the owner stored are lost.
"""

import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rail_passes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("first_day", sa.Date(), nullable=False),
        sa.Column("last_day", sa.Date(), nullable=False),
        sa.Column("day_cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("carriers", sa.String(300), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("last_day >= first_day", name="ck_rail_passes_days"),
        sa.CheckConstraint("day_cost >= 0", name="ck_rail_passes_not_negative"),
    )


def downgrade() -> None:
    op.drop_table("rail_passes")
