"""The travel class of a fare (#690).

Revision ID: 0017
Revises: 0016

No data change: the upgrade adds a nullable column (old fares have no known class); the downgrade drops it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("travel_class", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("fares", "travel_class")
