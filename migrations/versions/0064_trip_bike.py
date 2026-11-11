"""The bicycle of a trip (#2473): the trip takes a bicycle.

Revision ID: 0064
Revises: 0063

No data loss: the upgrade adds the column `trips.bike` (NOT NULL, default false); each existing trip gets false.
The downgrade drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("bike", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("trips", "bike")
