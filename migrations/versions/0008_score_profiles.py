"""The score profiles (#229).

Revision ID: 0008
Revises: 0007

No data change: the upgrade adds the table `score_profiles`; the downgrade drops it (and the saved profiles).
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "score_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("config_json", sa.JSON(), nullable=False),
    )
    op.create_index("uq_score_profiles_default", "score_profiles", ["is_default"], unique=True,
                    postgresql_where=sa.text("is_default"))


def downgrade() -> None:
    op.drop_index("uq_score_profiles_default", table_name="score_profiles")
    op.drop_table("score_profiles")
