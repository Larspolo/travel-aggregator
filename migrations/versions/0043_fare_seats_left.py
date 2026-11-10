"""The seats left of a fare (#1823), when the source gives a count.

Revision ID: 0043
Revises: 0042

No data loss: the upgrade adds the nullable column `fares.seats_left`. The downgrade drops only this new column and
its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("seats_left", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("fares", "seats_left")
