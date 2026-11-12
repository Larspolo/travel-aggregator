"""The series of the repeated copies of a trip (#2498).

Revision ID: 0065
Revises: 0064

No data loss: the upgrade adds the table `trip_series` and the column `trips.series_id` (NULL for each existing trip).
The downgrade drops only this new column and table and their values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("trip_series",
                    sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("step_weeks", sa.Integer(), nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column("trips", sa.Column("series_id", sa.Integer(),
                                     sa.ForeignKey("trip_series.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_trips_series_id", "trips", ["series_id"])


def downgrade() -> None:
    op.drop_index("ix_trips_series_id", table_name="trips")
    op.drop_column("trips", "series_id")
    op.drop_table("trip_series")
