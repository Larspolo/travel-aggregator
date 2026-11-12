"""The on-board services of a leg (#2548).

Revision ID: 0066
Revises: 0065

No data loss: the upgrade adds the column `legs.services` (NULL for each existing leg: not known).
The downgrade drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("legs", sa.Column("services", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("legs", "services")
