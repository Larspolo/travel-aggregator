"""The backup before a migration that changes data (app/backup.py)."""

import shutil
import subprocess
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app import backup

PG_BIN = Path("/usr/lib/postgresql/16/bin")


def _pg(name: str) -> str:
    return str(PG_BIN / name) if (PG_BIN / name).exists() else name


@pytest.fixture
def pg_tools(monkeypatch):
    if not (PG_BIN / "pg_dump").exists() and not shutil.which("pg_dump"):
        pytest.skip("no pg_dump")
    monkeypatch.setenv("PATH", f"{PG_BIN}:" + __import__("os").environ["PATH"])


def _cfg(tmp_path, marker, url, with_second=True):
    """A script directory: revision a (initial, creates a table) and, pending, revision b."""
    d = tmp_path / "mig"
    (d / "versions").mkdir(parents=True)
    (d / "env.py").write_text(
        "from alembic import context\nfrom sqlalchemy import create_engine\n"
        "e = create_engine(context.config.get_main_option('sqlalchemy.url'))\n"
        "with e.connect() as c:\n    context.configure(connection=c)\n"
        "    with context.begin_transaction():\n        context.run_migrations()\n")
    (d / "script.py.mako").write_text("")
    (d / "versions" / "a_first.py").write_text(
        "revision='a'\ndown_revision=None\nbranch_labels=None\ndepends_on=None\n"
        "from alembic import op\n"
        "def upgrade():\n    op.execute('CREATE TABLE t (x int)')\n    op.execute('INSERT INTO t VALUES (42)')\n"
        "def downgrade():\n    op.execute('DROP TABLE t')\n")
    if with_second:
        extra = "changes_data = True\n" if marker else ""
        (d / "versions" / "b_second.py").write_text(
            "revision='b'\ndown_revision='a'\nbranch_labels=None\ndepends_on=None\n" + extra +
            "from alembic import op\n"
            "def upgrade():\n    op.execute('DELETE FROM t')\ndef downgrade():\n    pass\n")
    cfg = Config()
    cfg.set_main_option("script_location", str(d))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _apply_first(cfg, url):
    # Run only revision a with a plain SQL stamp-free upgrade.
    command.upgrade(cfg, "a")


def test_marker_makes_dump_that_restores(pg_tools, empty_database_url, tmp_path):
    cfg = _cfg(tmp_path, True, empty_database_url)
    _apply_first(cfg, empty_database_url)
    out = tmp_path / "bk"
    target = backup.backup_if_needed(empty_database_url, out, cfg)
    assert target and target.exists() and target.name.endswith("-b.dump")
    command.upgrade(cfg, "head")  # the data is deleted now
    engine = create_engine(empty_database_url)
    with engine.begin() as c:
        assert c.execute(text("SELECT count(*) FROM t")).scalar() == 0
    engine.dispose()
    subprocess.run([_pg("pg_restore"), "--clean", "--if-exists", "--dbname", empty_database_url.replace("+psycopg", ""), str(target)],
                   capture_output=True)  # A newer client can warn (exit 1) about settings; the data check below decides.
    engine = create_engine(empty_database_url)
    with engine.connect() as c:
        assert c.execute(text("SELECT x FROM t")).scalar() == 42
    engine.dispose()


def test_no_marker_makes_no_dump(pg_tools, empty_database_url, tmp_path):
    cfg = _cfg(tmp_path, False, empty_database_url)
    _apply_first(cfg, empty_database_url)
    out = tmp_path / "bk"
    assert backup.backup_if_needed(empty_database_url, out, cfg) is None
    assert not out.exists() or not list(out.iterdir())


def test_fresh_database_with_marker_in_pending_dumps(pg_tools, empty_database_url, tmp_path):
    cfg = _cfg(tmp_path, True, empty_database_url)
    assert backup.pending_data_revisions(cfg, empty_database_url) == ["b"]


def test_failed_dump_raises_and_main_exits_1(pg_tools, empty_database_url, tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path, True, empty_database_url)
    _apply_first(cfg, empty_database_url)
    bad = empty_database_url.rsplit("/", 1)[0] + "/no_such_db"
    # The pending revisions are read from the real database; the dump goes to a missing one.
    monkeypatch.setattr(backup, "pending_data_revisions", lambda c, u: ["b"])
    with pytest.raises(backup.BackupError, match="pg_dump failed"):
        backup.backup_if_needed(bad, tmp_path / "bk", cfg)
    assert not list((tmp_path / "bk").glob("*.dump"))

    monkeypatch.setenv("DATABASE_URL", bad)
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    monkeypatch.setattr(backup, "backup_if_needed",
                        lambda url, d, cfg=None: (_ for _ in ()).throw(backup.BackupError("boom")))
    assert backup.main() == 1
    assert "migration not started" in capsys.readouterr().err
