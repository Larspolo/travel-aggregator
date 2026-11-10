"""The result of each sent message (#1812).

Revision ID: 0041
Revises: 0040

No data loss: the upgrade adds the new table `sent_messages`. The downgrade drops only this new table.
"""

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sent_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("click", sa.Text(), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sent_messages")
