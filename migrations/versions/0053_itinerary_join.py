"""The join of two itineraries of one trip (#2144): `itineraries.merged_into_id` and `fares.moved_from_id`.

Revision ID: 0053
Revises: 0052

No data change: the upgrade adds two nullable columns. The downgrade drops them: the joins go (the fares stay on
the row that they were joined into, and each joined row shows again as a row with no fare).
"""

import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("itineraries", sa.Column("merged_into_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_itineraries_merged_into_id", "itineraries", "itineraries", ["merged_into_id"], ["id"],
                          ondelete="CASCADE")
    op.create_index("ix_itineraries_merged_into_id", "itineraries", ["merged_into_id"])
    op.add_column("fares", sa.Column("moved_from_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_fares_moved_from_id", "fares", "itineraries", ["moved_from_id"], ["id"],
                          ondelete="SET NULL")
    op.create_index("ix_fares_moved_from_id", "fares", ["moved_from_id"])


def downgrade() -> None:
    op.drop_index("ix_fares_moved_from_id", table_name="fares")
    op.drop_constraint("fk_fares_moved_from_id", "fares", type_="foreignkey")
    op.drop_column("fares", "moved_from_id")
    op.drop_index("ix_itineraries_merged_into_id", table_name="itineraries")
    op.drop_constraint("fk_itineraries_merged_into_id", "itineraries", type_="foreignkey")
    op.drop_column("itineraries", "merged_into_id")
