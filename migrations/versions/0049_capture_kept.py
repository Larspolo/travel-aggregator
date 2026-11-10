"""The keep mark of a capture (#2018): the retention cleanup does not delete a kept capture.

Revision ID: 0049
Revises: 0048

No data loss: the upgrade adds the column `captures.kept` (NOT NULL, default false); the old captures become not kept.
The downgrade drops only this new column.
"""

import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("kept", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("captures", "kept")
