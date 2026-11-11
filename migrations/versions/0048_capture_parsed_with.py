"""The server parser version that parsed each capture (#1989): a capture parsed by an older parser can be found.

Revision ID: 0048
Revises: 0047

No data loss: the upgrade adds the nullable column `captures.parsed_with`; the old captures keep NULL. The downgrade
drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("parsed_with", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("captures", "parsed_with")
