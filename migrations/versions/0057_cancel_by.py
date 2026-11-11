"""The cancel time of a booked itinerary (#2311).

Revision ID: 0057
Revises: 0056

No data loss: the upgrade adds the nullable columns `itineraries.cancel_by` and `itineraries.cancel_by_offset_min`.
The downgrade drops only these new columns and their values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("itineraries", sa.Column("cancel_by", sa.DateTime(timezone=True), nullable=True))
    op.add_column("itineraries", sa.Column("cancel_by_offset_min", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("itineraries", "cancel_by_offset_min")
    op.drop_column("itineraries", "cancel_by")
