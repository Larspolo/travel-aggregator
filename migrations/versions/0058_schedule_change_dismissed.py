"""The dismissed timetable changes of a booked itinerary (#2342).

Revision ID: 0058
Revises: 0057

No data loss: the upgrade adds the nullable column `itineraries.schedule_change_dismissed`.
The downgrade drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("itineraries", sa.Column("schedule_change_dismissed", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("itineraries", "schedule_change_dismissed")
