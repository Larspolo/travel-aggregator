"""The access and egress places of one trip (#2108).

Revision ID: 0052
Revises: 0051

No data change: the upgrade adds the table `trip_access_times`; the downgrade drops it (and its rows).
"""

import sqlalchemy as sa
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trip_access_times",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("place_text", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(10, 2), nullable=False),
        sa.CheckConstraint("kind IN ('access', 'egress')", name="ck_trip_access_times_kind"),
        sa.CheckConstraint("minutes >= 0", name="ck_trip_access_times_minutes"),
        sa.CheckConstraint("cost >= 0", name="ck_trip_access_times_cost"),
    )
    op.create_index("uq_trip_access_times_place", "trip_access_times",
                    ["trip_id", "kind", sa.text("lower(trim(place_text))")], unique=True)


def downgrade() -> None:
    op.drop_table("trip_access_times")
