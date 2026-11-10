"""The server time of the insert of a capture (#1869): a resend tells a running first POST from a failed one.

Revision ID: 0046
Revises: 0045

No data loss: the upgrade adds the column `captures.received_at` with the default `now()` (the existing captures get
the time of the upgrade). The downgrade drops only this new column and its values.
"""

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                                        nullable=True))


def downgrade() -> None:
    op.drop_column("captures", "received_at")
