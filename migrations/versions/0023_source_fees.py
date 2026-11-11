"""The booking fee of each source (#1142): the score adds it (#1143).

Revision ID: 0023
Revises: 0022

No data change: the upgrade adds a new empty table; the downgrade drops it with its fees.
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_fees",
        sa.Column("source", sa.String(50), primary_key=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_source_fees_not_negative"),
    )


def downgrade() -> None:
    op.drop_table("source_fees")
