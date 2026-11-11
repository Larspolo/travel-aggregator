"""The key of a capture and the answer of its first POST, one capture per token and key (#1868).

Revision ID: 0045
Revises: 0044

No data loss: the upgrade adds the nullable columns `captures.token_id`, `captures.capture_key` and
`captures.answer_json` and a unique constraint on the token and the key. The downgrade drops only these new columns,
their values and the constraint.
"""

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("token_id", sa.Integer(),
                                        sa.ForeignKey("api_tokens.id", ondelete="SET NULL"), nullable=True))
    op.add_column("captures", sa.Column("capture_key", sa.String(64), nullable=True))
    op.add_column("captures", sa.Column("answer_json", sa.JSON(), nullable=True))
    op.create_unique_constraint("uq_captures_token_key", "captures", ["token_id", "capture_key"])


def downgrade() -> None:
    op.drop_constraint("uq_captures_token_key", "captures", type_="unique")
    op.drop_column("captures", "answer_json")
    op.drop_column("captures", "capture_key")
    op.drop_column("captures", "token_id")
