"""The booked flag of an itinerary (#201).

Revision ID: 0006
Revises: 0005

No data change: the upgrade adds a column with the default false (no offer is booked yet); the downgrade drops it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("itineraries", sa.Column("booked", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("itineraries", "booked")
