"""A backup on demand: `python -m app.backup --now` (app/backup.py)."""

import os
import shutil
from pathlib import Path

import pytest

from app import backup

PG_BIN = Path("/usr/lib/postgresql/16/bin")


@pytest.fixture
def pg_tools(monkeypatch):
    if not (PG_BIN / "pg_dump").exists() and not shutil.which("pg_dump"):
        pytest.skip("no pg_dump")
    monkeypatch.setenv("PATH", f"{PG_BIN}:" + os.environ["PATH"])


def test_now_writes_manual_dump(pg_tools, empty_database_url, tmp_path, monkeypatch, capsys):
    out = tmp_path / "bk"
    monkeypatch.setenv("DATABASE_URL", empty_database_url)
    monkeypatch.setenv("BACKUP_DIR", str(out))
    assert backup.main(["--now"]) == 0
    files = list(out.glob("*-manual.dump"))
    assert len(files) == 1 and files[0].stat().st_size > 0
    assert capsys.readouterr().out.strip() == str(files[0])


def test_now_failed_dump_exits_1_and_leaves_no_file(pg_tools, empty_database_url, tmp_path, monkeypatch, capsys):
    out = tmp_path / "bk"
    monkeypatch.setenv("DATABASE_URL", empty_database_url.rsplit("/", 1)[0] + "/no_such_db")
    monkeypatch.setenv("BACKUP_DIR", str(out))
    assert backup.main(["--now"]) == 1
    assert not list(out.glob("*.dump"))
    assert "backup failed" in capsys.readouterr().err
