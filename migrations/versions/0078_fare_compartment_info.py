"""The info texts of the compartment of a fare (#2787).

Revision ID: 0078
Revises: 0077

No data loss: the upgrade adds the column `fares.compartment_info` (null for each existing row).
The downgrade drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fares", sa.Column("compartment_info", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("fares", "compartment_info")
