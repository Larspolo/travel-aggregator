"""The stops of a leg (#2634).

Revision ID: 0071
Revises: 0070

No data loss: the upgrade adds the new table `leg_stops` (empty). The downgrade drops only this new table.
"""

import sqlalchemy as sa
from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leg_stops",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("leg_id", sa.Integer(), sa.ForeignKey("legs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(20), nullable=True),
        sa.Column("arrive_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arrive_offset_min", sa.Integer(), nullable=True),
        sa.Column("depart_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("depart_offset_min", sa.Integer(), nullable=True),
        sa.Column("platform", sa.String(10), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
    )
    op.create_index("ix_leg_stops_leg_id", "leg_stops", ["leg_id"])


def downgrade() -> None:
    op.drop_index("ix_leg_stops_leg_id", table_name="leg_stops")
    op.drop_table("leg_stops")
