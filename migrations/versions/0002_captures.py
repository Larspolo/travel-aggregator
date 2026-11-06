"""The captures table (raw payload as gzip) and fare_prices.capture_id.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "captures",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trip_id", sa.Integer, sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("parser_version", sa.String(50)),
        sa.Column("page_url", sa.String(2000)),
        sa.Column("search_context_json", sa.JSON),
        sa.Column("raw_gz", sa.LargeBinary),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("fare_prices", sa.Column("capture_id", sa.Integer,
                                           sa.ForeignKey("captures.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_fare_prices_capture_id", "fare_prices", ["capture_id"])


def downgrade() -> None:
    op.drop_index("ix_fare_prices_capture_id", table_name="fare_prices")
    op.drop_column("fare_prices", "capture_id")
    op.drop_table("captures")
