"""The end date of an API token (#1846).

Revision ID: 0044
Revises: 0043

No data loss: the upgrade adds the nullable column `api_tokens.expires_at`. The downgrade drops only this new column
and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_tokens", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("api_tokens", "expires_at")
