"""The operator cancel mark of an itinerary (#2629).

Revision ID: 0072
Revises: 0071

No data loss: the upgrade adds the column `itineraries.operator_cancelled_at` (NULL for each existing row).
The downgrade drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("itineraries", sa.Column("operator_cancelled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("itineraries", "operator_cancelled_at")
