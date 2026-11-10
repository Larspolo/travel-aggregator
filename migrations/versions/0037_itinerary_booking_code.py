"""The booking code of a booked itinerary (#1716).

Revision ID: 0037
Revises: 0036

No data loss: the upgrade adds the nullable column `itineraries.booking_code`. The downgrade drops only this new
column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("itineraries", sa.Column("booking_code", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("itineraries", "booking_code")
