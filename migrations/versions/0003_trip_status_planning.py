"""The trip status values of docs/SPEC.md section 2: a new trip has `planning`, not `active` (#73).

Revision ID: 0003
Revises: 0002

Data change: the upgrade changes the trips with `active` to `planning`. The downgrade cannot know which trips had
`active`, so it changes all `planning` trips to `active`.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("trips", "status", server_default="planning")
    op.execute("UPDATE trips SET status = 'planning' WHERE status = 'active'")


def downgrade() -> None:
    op.execute("UPDATE trips SET status = 'active' WHERE status = 'planning'")
    op.alter_column("trips", "status", server_default="active")
