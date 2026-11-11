"""The Alembic revision of the database and the head revision of the migrations (the version card, #1735)."""

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.orm import Session


def revisions(session: Session, cfg: Config | None = None) -> tuple[str | None, str | None]:
    """The current revision of the database and the head revision of `migrations/`.

    The first value is `None` for an empty database. The second is `None` when the scripts have more than one head.
    """
    cfg = cfg or Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    heads = MigrationContext.configure(session.connection()).get_current_heads()
    current = heads[0] if heads else None
    return current, script.get_current_head()
