"""The berth of a night-train fare (#1807): seat, couchette or sleeper.

Revision ID: 0042
Revises: 0041

No data loss: the upgrade adds the nullable column `fares.berth`. The downgrade drops only this new column and
its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("berth", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("fares", "berth")
