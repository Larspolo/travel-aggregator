"""The booked platforms of a leg (#2683).

Revision ID: 0075
Revises: 0074

No data loss: the upgrade adds the columns `legs.booked_from_platform` and `legs.booked_to_platform` (NULL for each
existing row). The downgrade drops only these new columns and their values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("legs", sa.Column("booked_from_platform", sa.String(10), nullable=True))
    op.add_column("legs", sa.Column("booked_to_platform", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("legs", "booked_to_platform")
    op.drop_column("legs", "booked_from_platform")
