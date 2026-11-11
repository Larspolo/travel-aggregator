"""The rail pass of a trip (#2266).

Revision ID: 0056
Revises: 0055

No data loss of the passes: the upgrade adds the nullable column `trips.rail_pass_id` (a foreign key to
`rail_passes.id`, set to NULL when the pass is deleted). The downgrade drops this column, so the rail pass that
each trip chose is lost; the trips and their offers stay.
"""

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("rail_pass_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_trips_rail_pass_id", "trips", "rail_passes", ["rail_pass_id"], ["id"],
                          ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_trips_rail_pass_id", "trips", type_="foreignkey")
    op.drop_column("trips", "rail_pass_id")
