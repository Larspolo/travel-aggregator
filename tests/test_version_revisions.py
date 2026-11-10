"""The revision of the database and the head of the migrations (app/version.py, #1737)."""

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db import make_engine, make_sessionmaker
from app.version import revisions


def _alembic(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


def test_head_database_has_the_head_of_the_scripts(migrated_url):
    engine = make_engine(migrated_url)
    try:
        with make_sessionmaker(engine)() as session:
            current, head = revisions(session)
    finally:
        engine.dispose()
    assert head is not None
    assert current == head


def test_downgrade_moves_the_database_value_and_keeps_the_head(migrated_url):
    cfg = _alembic(migrated_url)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    before_head = ScriptDirectory.from_config(cfg).get_revision(head).down_revision
    command.downgrade(cfg, before_head)

    engine = make_engine(migrated_url)
    try:
        with make_sessionmaker(engine)() as session:
            current, new_head = revisions(session, cfg)
    finally:
        engine.dispose()
    assert current == before_head
    assert new_head == head
    command.upgrade(cfg, "head")
