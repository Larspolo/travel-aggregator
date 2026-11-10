"""The last day of the share link of a trip (#2026).

Revision ID: 0051
Revises: 0050

No data change: the upgrade adds the nullable column `trips.share_ends_on`; the downgrade drops it (and its values).
"""

import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("share_ends_on", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "share_ends_on")
