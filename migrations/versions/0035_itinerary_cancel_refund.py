"""The cancel time and the refund of a booked itinerary (#1685).

Revision ID: 0035
Revises: 0034

No data loss: the upgrade adds the nullable columns `itineraries.cancelled_at` and `itineraries.refund_price`. The
downgrade drops only these new columns and their values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("itineraries", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("itineraries", sa.Column("refund_price", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("itineraries", "refund_price")
    op.drop_column("itineraries", "cancelled_at")
