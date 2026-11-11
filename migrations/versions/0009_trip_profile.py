"""The score profile of a trip (#232).

Revision ID: 0009
Revises: 0008

No data change: the upgrade adds the nullable column `trips.profile_id`; the downgrade drops it (the profile choice of
each trip is lost, the trips keep their offers). A profile that is deleted sets the column to NULL.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("profile_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_trips_profile_id", "trips", "score_profiles", ["profile_id"], ["id"],
                          ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_trips_profile_id", "trips", type_="foreignkey")
    op.drop_column("trips", "profile_id")
