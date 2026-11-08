"""The daily backup: `python -m app.backup --daily` runs one step of its loop (app/backup.py)."""

import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app import backup

PG_BIN = Path("/usr/lib/postgresql/16/bin")
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
DAY = timedelta(hours=24)


@pytest.fixture
def pg_tools(monkeypatch):
    if not (PG_BIN / "pg_dump").exists() and not shutil.which("pg_dump"):
        pytest.skip("no pg_dump")
    monkeypatch.setenv("PATH", f"{PG_BIN}:" + os.environ["PATH"])


def test_step_writes_a_daily_dump_when_none_exists(pg_tools, empty_database_url, tmp_path):
    out = tmp_path / "bk"
    wait = backup.daily_step(empty_database_url, out, DAY, now=NOW)
    files = list(out.glob("*-daily.dump"))
    assert len(files) == 1 and files[0].stat().st_size > 0
    assert wait == DAY.total_seconds()


def test_step_writes_nothing_when_the_newest_daily_is_one_hour_old(empty_database_url, tmp_path, capsys):
    out = tmp_path / "bk"
    out.mkdir()
    one_hour_ago = NOW - timedelta(hours=1)
    (out / f"{one_hour_ago:%Y%m%dT%H%M%SZ}-daily.dump").write_bytes(b"old")
    wait = backup.daily_step(empty_database_url, out, DAY, now=NOW)
    assert [p.name for p in out.glob("*.dump")] == [f"{one_hour_ago:%Y%m%dT%H%M%SZ}-daily.dump"]
    assert wait == (DAY - timedelta(hours=1)).total_seconds()
    assert capsys.readouterr().err == ""


def test_manual_dump_does_not_count_as_the_daily_one(pg_tools, empty_database_url, tmp_path):
    out = tmp_path / "bk"
    out.mkdir()
    (out / f"{NOW - timedelta(hours=1):%Y%m%dT%H%M%SZ}-manual.dump").write_bytes(b"manual")
    wait = backup.daily_step(empty_database_url, out, DAY, now=NOW)
    assert len(list(out.glob("*-daily.dump"))) == 1
    assert wait == DAY.total_seconds()


def test_failed_dump_prints_the_error_and_retries_after_one_hour(empty_database_url, tmp_path, capsys):
    out = tmp_path / "bk"
    bad_url = empty_database_url.rsplit("/", 1)[0] + "/no_such_db"
    wait = backup.daily_step(bad_url, out, DAY, now=NOW)
    assert wait == 3600.0
    err = capsys.readouterr().err
    assert err.startswith("ERROR: daily backup failed: ")
    assert not list(out.glob("*.dump"))


@pytest.mark.parametrize("compose", ["docker-compose.yml", "deploy/production/docker-compose.yml"])
def test_compose_has_the_backup_service(compose):
    import yaml

    root = Path(__file__).resolve().parent.parent
    service = yaml.safe_load((root / compose).read_text(encoding="utf-8"))["services"]["backup"]
    assert service["command"] == "python -m app.backup --daily"
    assert service["env_file"] == ".env"
    assert service["restart"] == "unless-stopped"
    assert "db" in service["depends_on"]
    assert any(v.endswith(":/backups") for v in service["volumes"])
