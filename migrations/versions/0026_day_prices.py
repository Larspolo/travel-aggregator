"""The day prices of a capture (#1197).

Revision ID: 0026
Revises: 0025

No data change: the upgrade adds the table `day_prices`; the downgrade drops it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "day_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capture_id", sa.Integer(), sa.ForeignKey("captures.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("source", "trip_id", "day", name="uq_day_prices_source_trip_day"),
    )
    op.create_index("ix_day_prices_trip_id", "day_prices", ["trip_id"])
    op.create_index("ix_day_prices_capture_id", "day_prices", ["capture_id"])


def downgrade() -> None:
    op.drop_index("ix_day_prices_capture_id", table_name="day_prices")
    op.drop_index("ix_day_prices_trip_id", table_name="day_prices")
    op.drop_table("day_prices")
