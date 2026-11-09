"""The log of the login attempts (#1353).

Revision ID: 0028
Revises: 0027

No data change: the upgrade adds the table `login_events`; the downgrade drops it (and its rows).
"""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("address", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(300), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("login_events")
