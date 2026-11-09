"""The count of legs with a mandatory seat reservation of a fare (#1620).

Revision ID: 0033
Revises: 0032

No data loss: the upgrade adds the column `fares.reservation_legs` (not null, default 0). The downgrade drops only
this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("reservation_legs", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("fares", "reservation_legs")
