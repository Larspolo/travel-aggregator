"""The notices of the operator for an itinerary (#2624).

Revision ID: 0070
Revises: 0069

No data loss: the upgrade adds the column `itineraries.notices` (NULL for each existing itinerary: not known).
The downgrade drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("itineraries", sa.Column("notices", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("itineraries", "notices")
