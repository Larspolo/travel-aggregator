"""The initial tables: trips, itineraries, legs, fares, fare_prices, api_tokens.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)
MONEY = sa.Numeric(10, 2)


def upgrade() -> None:
    op.create_table(
        "trips",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("origin_text", sa.String(200)),
        sa.Column("destination_text", sa.String(200)),
        sa.Column("date_from", sa.Date),
        sa.Column("date_to", sa.Date),
        sa.Column("travelers", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "itineraries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trip_id", sa.Integer, sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column("mode_summary", sa.String(100)),
        sa.Column("depart_at", TZ, nullable=False),
        sa.Column("arrive_at", TZ, nullable=False),
        sa.Column("duration_min", sa.Integer, nullable=False),
        sa.Column("transfers", sa.Integer, nullable=False, server_default="0"),
        sa.Column("first_seen_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("hidden", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("pinned", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("note", sa.Text),
        sa.UniqueConstraint("trip_id", "fingerprint", name="uq_itineraries_trip_fingerprint"),
    )
    op.create_table(
        "legs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("itinerary_id", sa.Integer, sa.ForeignKey("itineraries.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("carrier", sa.String(100)),
        sa.Column("service_no", sa.String(50)),
        sa.Column("from_name", sa.String(200), nullable=False),
        sa.Column("from_code", sa.String(20)),
        sa.Column("to_name", sa.String(200), nullable=False),
        sa.Column("to_code", sa.String(20)),
        sa.Column("depart_at", TZ, nullable=False),
        sa.Column("depart_offset_min", sa.Integer, nullable=False),
        sa.Column("arrive_at", TZ, nullable=False),
        sa.Column("arrive_offset_min", sa.Integer, nullable=False),
        sa.UniqueConstraint("itinerary_id", "seq", name="uq_legs_itinerary_seq"),
    )
    op.create_table(
        "fares",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("itinerary_id", sa.Integer, sa.ForeignKey("itineraries.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("fare_name", sa.String(100)),
        sa.Column("flexibility", sa.String(50)),
        sa.Column("booking_url", sa.Text),
        sa.Column("latest_price", MONEY, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("latest_captured_at", TZ, nullable=False),
    )
    op.create_table(
        "fare_prices",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("fare_id", sa.Integer, sa.ForeignKey("fares.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("price", MONEY, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("captured_at", TZ, nullable=False),
    )
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", TZ),
        sa.Column("revoked_at", TZ),
    )


def downgrade() -> None:
    for table in ("api_tokens", "fare_prices", "fares", "legs", "itineraries", "trips"):
        op.drop_table(table)
