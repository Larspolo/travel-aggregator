"""The trip warning of the last parse of each capture (#556).

Revision ID: 0016
Revises: 0015

No data change: the upgrade adds the nullable column `mismatch` (`places` or `date`) to `captures`; the old captures
keep NULL. The downgrade drops it (the stored warnings are lost, the captures and their offers stay).
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("mismatch", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("captures", "mismatch")
