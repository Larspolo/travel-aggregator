"""The seen price of a fare (#355).

Revision ID: 0012
Revises: 0011

No data change: the upgrade adds the nullable column `fares.seen_price` (the price at the last view of the trip page);
the downgrade drops it (the next view after an upgrade shows no old drops).
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("seen_price", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("fares", "seen_price")
