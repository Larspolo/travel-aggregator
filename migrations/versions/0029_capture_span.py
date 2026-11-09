"""The departure span of a capture (#1404): the gone check needs it also when all prices of the capture are steady.

Revision ID: 0029
Revises: 0028

No data loss: the upgrade adds the nullable columns `captures.depart_from` and `captures.depart_to` and fills them for
the old captures from their price rows (the rule of #1385: the min and max departure of the fares that the capture
priced). The downgrade drops the two columns; the price rows stay.
"""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("depart_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("captures", sa.Column("depart_to", sa.DateTime(timezone=True), nullable=True))
    op.execute("""
        UPDATE captures SET depart_from = s.low, depart_to = s.high
        FROM (SELECT fp.capture_id, min(i.depart_at) AS low, max(i.depart_at) AS high
              FROM fare_prices fp JOIN fares f ON f.id = fp.fare_id JOIN itineraries i ON i.id = f.itinerary_id
              WHERE fp.capture_id IS NOT NULL GROUP BY fp.capture_id) AS s
        WHERE s.capture_id = captures.id
    """)


def downgrade() -> None:
    op.drop_column("captures", "depart_to")
    op.drop_column("captures", "depart_from")
