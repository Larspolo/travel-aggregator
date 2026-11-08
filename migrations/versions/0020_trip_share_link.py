"""The secret share link of a trip (#903): the hash of its token and the time of the share.

Revision ID: 0020
Revises: 0019

No data change: the upgrade adds two nullable columns (old trips have no link); the downgrade drops them.
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("share_hash", sa.String(128), nullable=True))
    op.add_column("trips", sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("trips_share_hash_key", "trips", ["share_hash"])


def downgrade() -> None:
    op.drop_constraint("trips_share_hash_key", "trips", type_="unique")
    op.drop_column("trips", "shared_at")
    op.drop_column("trips", "share_hash")
