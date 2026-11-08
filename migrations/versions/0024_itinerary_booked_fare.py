"""The paid fare, price and time of the mark "booked" (#1146).

Revision ID: 0024
Revises: 0023

No data change: the upgrade adds four nullable columns (old booked rows have no paid price); the downgrade drops
them with their values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("itineraries", sa.Column("booked_fare_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_itineraries_booked_fare_id", "itineraries", "fares", ["booked_fare_id"], ["id"],
                          ondelete="SET NULL")
    op.add_column("itineraries", sa.Column("booked_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("itineraries", sa.Column("booked_currency", sa.String(3), nullable=True))
    op.add_column("itineraries", sa.Column("booked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("itineraries", "booked_at")
    op.drop_column("itineraries", "booked_currency")
    op.drop_column("itineraries", "booked_price")
    op.drop_constraint("fk_itineraries_booked_fare_id", "itineraries", type_="foreignkey")
    op.drop_column("itineraries", "booked_fare_id")
