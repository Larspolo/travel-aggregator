"""The result of the last parse of each capture (#346).

Revision ID: 0010
Revises: 0009

No data change: the upgrade adds the nullable columns `offer_count`, `rejected_count`, `errors_json` and `unreadable`
to `captures` (the old captures keep NULL); the downgrade drops them (the stored parse results are lost, the captures
and their offers stay).
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("offer_count", sa.Integer(), nullable=True))
    op.add_column("captures", sa.Column("rejected_count", sa.Integer(), nullable=True))
    op.add_column("captures", sa.Column("errors_json", sa.JSON(), nullable=True))
    op.add_column("captures", sa.Column("unreadable", sa.String(200), nullable=True))


def downgrade() -> None:
    for name in ("unreadable", "errors_json", "rejected_count", "offer_count"):
        op.drop_column("captures", name)
