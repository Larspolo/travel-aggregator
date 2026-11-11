"""The checked bag of a trip (#2397).

Revision ID: 0061
Revises: 0060

No data loss: the upgrade adds the nullable column `trips.checked_bag`.
The downgrade drops only this new column.
"""

import sqlalchemy as sa
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("checked_bag", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "checked_bag")
