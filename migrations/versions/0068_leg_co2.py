"""The CO2 grams of a leg (#2586).

Revision ID: 0068
Revises: 0067

No data loss: the upgrade adds the column `legs.co2_g` (NULL for each existing leg: not known).
The downgrade drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("legs", sa.Column("co2_g", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("legs", "co2_g")
