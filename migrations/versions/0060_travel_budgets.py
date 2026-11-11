"""The travel budget per year (#2375).

Revision ID: 0060
Revises: 0059

No data loss: the upgrade adds the table `travel_budgets`.
The downgrade drops only this new table and its budgets.
"""

import sqlalchemy as sa
from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "travel_budgets",
        sa.Column("year", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_travel_budgets_not_negative"),
        sa.PrimaryKeyConstraint("year"),
    )


def downgrade() -> None:
    op.drop_table("travel_budgets")
