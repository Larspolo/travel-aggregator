"""`migrated_url` copies a database that was migrated once per test process (tests/conftest.py, #1070).

The copy must be the same as a database with all migrations, and a test must not change the database of a later test.
"""

from alembic.script import ScriptDirectory
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _head():
    return ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()


def _tables(url):
    engine = create_engine(url)
    try:
        with engine.connect() as c:
            version = c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        return version, set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_the_copy_has_all_migrations_as_an_upgrade_from_empty(migrated_url, empty_database_url):
    from tests.conftest import _upgrade

    _upgrade(empty_database_url)
    assert _tables(migrated_url) == _tables(empty_database_url)
    assert _tables(migrated_url)[0] == _head()


def test_a_change_in_a_copy_is_not_in_the_next_copy(migrated_url, migrated_template, postgres_url):
    from tests.conftest import _database

    assert migrated_url.rsplit("/", 1)[1] != migrated_template
    engine = create_engine(migrated_url)
    try:
        with engine.begin() as c:
            c.execute(text("CREATE TABLE written_by_a_test (id int)"))
    finally:
        engine.dispose()
    with _database(postgres_url, template=migrated_template) as next_url:
        assert next_url != migrated_url
        assert "written_by_a_test" not in _tables(next_url)[1]
        assert _tables(next_url) == _tables(migrated_url)[:1] + (_tables(migrated_url)[1] - {"written_by_a_test"},)
