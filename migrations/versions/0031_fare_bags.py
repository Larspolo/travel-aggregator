"""The checked bags of a fare (#1525).

Revision ID: 0031
Revises: 0030

No data loss: the upgrade adds the nullable columns `fares.checked_bags_included` and `fares.checked_bag_price`. The
downgrade drops the two columns and their values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("checked_bags_included", sa.Integer(), nullable=True))
    op.add_column("fares", sa.Column("checked_bag_price", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("fares", "checked_bag_price")
    op.drop_column("fares", "checked_bags_included")
