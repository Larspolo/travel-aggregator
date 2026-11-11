"""The bicycle transport of a fare (#2457): allowed, reservation or no.

Revision ID: 0063
Revises: 0062

No data loss: the upgrade adds the nullable column `fares.bike`. The downgrade drops only this new column and
its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("bike", sa.String(12), nullable=True))


def downgrade() -> None:
    op.drop_column("fares", "bike")
