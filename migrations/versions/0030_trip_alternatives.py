"""The other origins and destinations of a trip (#1422).

Revision ID: 0030
Revises: 0029

No data loss: the upgrade adds the nullable columns `trips.origin_alt_text` and `trips.destination_alt_text`. The
downgrade drops the two columns and their text.
"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("origin_alt_text", sa.String(200), nullable=True))
    op.add_column("trips", sa.Column("destination_alt_text", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "destination_alt_text")
    op.drop_column("trips", "origin_alt_text")
