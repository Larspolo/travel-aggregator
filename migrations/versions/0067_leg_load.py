"""The expected load of each class of a leg (#2582).

Revision ID: 0067
Revises: 0066

No data loss: the upgrade adds the columns `legs.load_first` and `legs.load_second` (NULL for each existing leg: not known).
The downgrade drops only these new columns and their values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("legs", sa.Column("load_first", sa.SmallInteger(), nullable=True))
    op.add_column("legs", sa.Column("load_second", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("legs", "load_second")
    op.drop_column("legs", "load_first")
