"""The "leave after" time of a trip (#2023).

Revision ID: 0050
Revises: 0049

No data change: the upgrade adds the nullable column `trips.leave_after`; the downgrade drops it (and its values).
"""

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("leave_after", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "leave_after")
