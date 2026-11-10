"""The tags of a trip (#1950).

Revision ID: 0047
Revises: 0046

No data loss: the upgrade adds the nullable column `trips.tags_text`. The downgrade drops the column and its tags.
"""

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("tags_text", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "tags_text")
