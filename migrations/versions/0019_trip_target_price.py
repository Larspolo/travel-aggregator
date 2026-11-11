"""The target price of a trip (#846): the fares at or below it are marked.

Revision ID: 0019
Revises: 0018

No data change: the upgrade adds a nullable column (old trips have no target); the downgrade drops it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("target_price", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "target_price")
