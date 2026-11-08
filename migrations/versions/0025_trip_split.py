"""The split trips of a trip via a place (#1177).

Revision ID: 0025
Revises: 0024

No data change: the upgrade adds one nullable column; the downgrade drops it (the split trips stay as plain trips).
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("split_of_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_trips_split_of_id", "trips", "trips", ["split_of_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_trips_split_of_id", "trips", ["split_of_id"])


def downgrade() -> None:
    op.drop_index("ix_trips_split_of_id", table_name="trips")
    op.drop_constraint("fk_trips_split_of_id", "trips", type_="foreignkey")
    op.drop_column("trips", "split_of_id")
