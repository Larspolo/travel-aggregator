"""The "Suits me" marks of the travel partner on the read-only link of a trip (#1781).

Revision ID: 0040
Revises: 0039

No data loss: the upgrade adds the new table `share_marks`. The downgrade drops only this new table and its marks.
"""

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "share_marks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("itinerary_id", sa.Integer(), sa.ForeignKey("itineraries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("trip_id", "itinerary_id", name="uq_share_marks_trip_itinerary"),
    )
    op.create_index("ix_share_marks_trip_id", "share_marks", ["trip_id"])
    op.create_index("ix_share_marks_itinerary_id", "share_marks", ["itinerary_id"])


def downgrade() -> None:
    op.drop_index("ix_share_marks_itinerary_id", table_name="share_marks")
    op.drop_index("ix_share_marks_trip_id", table_name="share_marks")
    op.drop_table("share_marks")
