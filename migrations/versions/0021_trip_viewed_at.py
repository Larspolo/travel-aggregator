"""The time of the last full view of a trip page (#1090): the rows after it are "new".

Revision ID: 0021
Revises: 0020

No data change: the upgrade adds one nullable column (old trips have no view); the downgrade drops it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "viewed_at")
