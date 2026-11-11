"""The time of the travel-day message of a booked itinerary (#1648).

Revision ID: 0034
Revises: 0033

No data loss: the upgrade adds the nullable column `itineraries.travel_day_sent_at`. The downgrade drops only this
new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("itineraries", sa.Column("travel_day_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("itineraries", "travel_day_sent_at")
