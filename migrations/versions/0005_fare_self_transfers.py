"""The count of self-transfers of a fare (#176).

Revision ID: 0005
Revises: 0004

No data change: the upgrade adds a column with the default 0 (each old fare is one ticket); the downgrade drops it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("self_transfers", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("fares", "self_transfers")
