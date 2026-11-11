"""The place names of the owner, merged with the built-in table (#2215, epic #2214)."""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.models import PlaceName
from app.place_names import aliases
from app.tripmatch import ALIASES


def _alembic(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


def _rows(sessions, *pairs):
    with sessions() as s:
        s.add_all([PlaceName(city=c, name=n) for c, n in pairs])
        s.commit()


def test_owner_names_join_the_built_in_groups_or_make_new_ones(sessions):
    _rows(sessions, ("Paris", "Parijs"), ("antwerp", "Antwerpen"), ("Köln", "Keulen"))
    with sessions() as s:
        merged = aliases(s)
    assert merged["Paris"] == ("Parijs",)
    assert merged["antwerp"] == ("Antwerpen",)
    assert merged["Cologne"] == ("Köln", "Koln", "Keulen")
    assert all(merged[k] == v for k, v in ALIASES.items() if k != "Cologne")
    assert len(merged) == len(ALIASES) + 2


def test_no_rows_give_the_built_in_table(sessions):
    with sessions() as s:
        assert aliases(s) == ALIASES


def test_the_built_in_table_is_not_changed(sessions):
    _rows(sessions, ("Zürich", "Zurich-Hbf"))
    with sessions() as s:
        aliases(s)
    assert ALIASES["Zurich"] == ("Zürich", "Zuerich", "ZRH")


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "0054")
    engine = create_engine(empty_database_url)
    try:
        assert "place_names" in inspect(engine).get_table_names()
        command.downgrade(cfg, "0053")
        assert "place_names" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
