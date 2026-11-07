"""The settings table of the settings page (#207).

Revision ID: 0007
Revises: 0006

No data change: the upgrade adds an empty table; the downgrade drops it (the saved settings go, the defaults apply).
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("settings")
