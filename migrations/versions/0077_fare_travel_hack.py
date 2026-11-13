"""The hidden-city or throwaway mark of a fare (#2793).

Revision ID: 0077
Revises: 0076

No data loss: the upgrade adds the column `fares.travel_hack` (null for each existing row).
The downgrade drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("travel_hack", sa.String(12), nullable=True))


def downgrade() -> None:
    op.drop_column("fares", "travel_hack")
