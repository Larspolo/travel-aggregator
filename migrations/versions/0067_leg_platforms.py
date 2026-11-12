"""The planned platforms of a leg (#2590).

Revision ID: 0067
Revises: 0066

No data loss: the upgrade adds the columns `legs.from_platform` and `legs.to_platform` (NULL: not known).
The downgrade drops only these new columns and their values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("legs", sa.Column("from_platform", sa.String(10), nullable=True))
    op.add_column("legs", sa.Column("to_platform", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("legs", "to_platform")
    op.drop_column("legs", "from_platform")
