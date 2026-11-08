"""The time of the last reminder of a trip (#1118): a trip gets one reminder each N days.

Revision ID: 0022
Revises: 0021

No data change: the upgrade adds one nullable column (old trips have no reminder); the downgrade drops it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "reminded_at")
