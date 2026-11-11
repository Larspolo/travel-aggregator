"""The days off of the owner (#2370): the new table `days_off`.

Revision ID: 0060
Revises: 0058

No data loss: the upgrade adds the new table `days_off`. The downgrade drops only this new table, so the
days off that the owner stored are lost.
"""

import sqlalchemy as sa
from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "days_off",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("first_day", sa.Date(), nullable=False),
        sa.Column("last_day", sa.Date(), nullable=False),
        sa.Column("note", sa.String(100), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("last_day >= first_day", name="ck_days_off_days"),
    )


def downgrade() -> None:
    op.drop_table("days_off")
