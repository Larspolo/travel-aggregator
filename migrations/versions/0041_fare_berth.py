"""The berth of a night-train fare (#1807): seat, couchette or sleeper.

Revision ID: 0041
Revises: 0040

No data loss: the upgrade adds the nullable column `fares.berth`. The downgrade drops only this new column and
its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("berth", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("fares", "berth")
