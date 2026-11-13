"""The compartment of a fare (#2786).

Revision ID: 0075
Revises: 0074

No data loss: the upgrade adds the column `fares.compartment` (null for each existing row).
The downgrade drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("compartment", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("fares", "compartment")
