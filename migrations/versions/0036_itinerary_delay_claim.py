"""The arrival delay and the claim payment time of a booked itinerary (#1691).

Revision ID: 0036
Revises: 0035

No data loss: the upgrade adds the nullable columns `itineraries.delay_min` and `itineraries.claim_paid_at`. The
downgrade drops only these new columns and their values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("itineraries", sa.Column("delay_min", sa.Integer(), nullable=True))
    op.add_column("itineraries", sa.Column("claim_paid_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("itineraries", "claim_paid_at")
    op.drop_column("itineraries", "delay_min")
