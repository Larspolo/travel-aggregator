"""The "arrive by" time of a trip (#1294).

Revision ID: 0027
Revises: 0026

No data change: the upgrade adds the nullable column `trips.arrive_by`; the downgrade drops it (and its values).
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("arrive_by", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "arrive_by")
