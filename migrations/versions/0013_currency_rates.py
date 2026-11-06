"""The exchange rates to EUR (#383).

Revision ID: 0013
Revises: 0012

No data change: the upgrade creates the table `currency_rates` (one rate to EUR per currency code); the downgrade
drops it, with the rates that it holds.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "currency_rates",
        sa.Column("code", sa.String(3), primary_key=True),
        sa.Column("eur_per_unit", sa.Numeric(14, 6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("eur_per_unit > 0", name="ck_currency_rates_positive"),
    )


def downgrade() -> None:
    op.drop_table("currency_rates")
