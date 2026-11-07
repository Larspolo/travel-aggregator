"""The number of travelers of a capture (#764).

Revision ID: 0018
Revises: 0017

No data change: the upgrade adds a nullable column (old captures have no known count); the downgrade drops it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("travelers", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("captures", "travelers")
