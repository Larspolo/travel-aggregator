"""The return trip of a trip (#340).

Revision ID: 0011
Revises: 0010

No data change: the upgrade adds the nullable, unique column `trips.return_of_id` (a foreign key to `trips.id`); the
downgrade drops it (the links between the outbound and the return trips are lost, both trips stay). Deleting the
outbound trip sets the column of its return trip to NULL.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("return_of_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_trips_return_of_id", "trips", "trips", ["return_of_id"], ["id"], ondelete="SET NULL")
    op.create_unique_constraint("uq_trips_return_of_id", "trips", ["return_of_id"])


def downgrade() -> None:
    op.drop_constraint("uq_trips_return_of_id", "trips", type_="unique")
    op.drop_constraint("fk_trips_return_of_id", "trips", type_="foreignkey")
    op.drop_column("trips", "return_of_id")
