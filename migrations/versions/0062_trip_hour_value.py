"""The hour value of a trip (#2422).

Revision ID: 0062
Revises: 0061

No data loss: the upgrade adds the nullable column `trips.hour_value`.
The downgrade drops only this new column.
"""

import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("hour_value", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "hour_value")
