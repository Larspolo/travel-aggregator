"""The results pages with no offers seen (#1755).

Revision ID: 0038
Revises: 0037

No data loss: the upgrade adds the new table `silent_page`. The downgrade drops only this new table and its rows.
"""

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "silent_page",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("page_url", sa.String(2000), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("script_version", sa.String(50), nullable=False),
    )
    op.create_index("ix_silent_page_source", "silent_page", ["source"])


def downgrade() -> None:
    op.drop_index("ix_silent_page_source", table_name="silent_page")
    op.drop_table("silent_page")
