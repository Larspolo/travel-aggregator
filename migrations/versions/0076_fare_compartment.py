"""The compartment of a fare (#2786).

Revision ID: 0076
Revises: 0075

No data loss: the upgrade adds the column `fares.compartment` (null for each existing row).
The downgrade drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("compartment", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("fares", "compartment")
