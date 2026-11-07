"""The table of access and egress places (docs/SPEC.md section 6, #97).

Revision ID: 0004
Revises: 0003

No data change: the upgrade adds a table; the downgrade drops it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_times",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("place_text", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(10, 2), nullable=False),
        sa.CheckConstraint("kind IN ('access', 'egress')", name="ck_access_times_kind"),
        sa.CheckConstraint("minutes >= 0", name="ck_access_times_minutes"),
        sa.CheckConstraint("cost >= 0", name="ck_access_times_cost"),
    )


def downgrade() -> None:
    op.drop_table("access_times")
