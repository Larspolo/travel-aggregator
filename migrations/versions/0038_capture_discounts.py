"""The discount cards of the travelers of a capture (#1750).

Revision ID: 0038
Revises: 0037

No data loss: the upgrade adds the nullable column `captures.discounts`. The downgrade drops only this new column
and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("discounts", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("captures", "discounts")
