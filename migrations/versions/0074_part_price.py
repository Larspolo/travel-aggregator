"""The part price mark of a fare (#2655).

Revision ID: 0074
Revises: 0073

No data loss: the upgrade adds the column `fares.part_price` (false for each existing row).
The downgrade drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("part_price", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("fares", "part_price")
