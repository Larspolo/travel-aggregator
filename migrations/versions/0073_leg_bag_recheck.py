"""The bag recheck mark of a leg (#2660).

Revision ID: 0073
Revises: 0072

No data loss: the upgrade adds the column `legs.bag_recheck` (NULL for each existing row).
The downgrade drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("legs", sa.Column("bag_recheck", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("legs", "bag_recheck")
