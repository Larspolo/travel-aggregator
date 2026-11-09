"""The whole check of a daily dump: real pg_dump and pg_restore, then the settings page (#1516)."""

import os
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import backup, notify
from app.auth import make_password_hash
from app.main import app
from app.models import Setting

PG_BIN = Path("/usr/lib/postgresql/16/bin")
PASSWORD = "pw"
DAY = timedelta(hours=24)
HOUR = timedelta(hours=1)
OLD_STAMP = "20260101T000000Z"


@pytest.fixture
def pg_tools(monkeypatch):
    if not (PG_BIN / "pg_dump").exists() and not shutil.which("pg_dump"):
        pytest.skip("no pg_dump")
    monkeypatch.setenv("PATH", f"{PG_BIN}:" + os.environ["PATH"])


@pytest.fixture
def backup_dir(tmp_path):
    d = tmp_path / "bk"
    d.mkdir()
    return d


@pytest.fixture
def sent(monkeypatch, sessions):
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value="ntfy"))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value="https://ntfy.example/topic"))
        s.commit()
    calls = []
    monkeypatch.setattr(notify, "post", lambda url, text, headers: calls.append(headers["Title"]))
    return calls


@pytest.fixture
def client(sessions, monkeypatch, backup_dir):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


@pytest.fixture
def cut_off_dump(monkeypatch):
    """The real dump, then the first half of its bytes only (a dump cut off on the disk)."""
    real_dump = backup.dump

    def dump(url, d, label):
        p = real_dump(url, d, label)
        data = p.read_bytes()
        p.write_bytes(data[: len(data) // 2])
        return p

    monkeypatch.setattr(backup, "dump", dump)


def _now():
    return datetime.now(UTC)


def test_good_daily_dump_shows_checked_on_settings(pg_tools, migrated_url, sessions, sent, client, backup_dir):
    now = _now()
    assert backup.daily_step(migrated_url, backup_dir, DAY, now=now) == DAY.total_seconds()
    html = client.get("/settings").text
    match = re.search(r"Checked: (\d+) tables", html)
    assert match and int(match.group(1)) >= 1
    assert "Check failed" not in html
    assert sent == []


def test_cut_off_daily_dump_shows_check_failed(pg_tools, migrated_url, sessions, sent, client, backup_dir,
                                               cut_off_dump):
    now = _now()
    assert backup.daily_step(migrated_url, backup_dir, DAY, now=now) == 3600.0
    html = client.get("/settings").text
    assert "Check failed" in html
    assert "Checked:" not in html
    assert sent == ["Backup failed"]
    assert list(backup_dir.glob("*-daily.dump")) == []
    assert len(list(backup_dir.glob("*-daily.dump.failed"))) == 1


def test_retry_after_cut_off_dump_writes_good_dump(pg_tools, migrated_url, sessions, sent, client, backup_dir,
                                                   monkeypatch):
    real_dump = backup.dump
    cut = {"on": True}

    def dump(url, d, label):
        p = real_dump(url, d, label)
        if cut["on"]:
            data = p.read_bytes()
            p.write_bytes(data[: len(data) // 2])
        return p

    monkeypatch.setattr(backup, "dump", dump)
    now = _now()
    assert backup.daily_step(migrated_url, backup_dir, DAY, now=now) == 3600.0
    assert "Check failed" in client.get("/settings").text

    cut["on"] = False
    assert backup.daily_step(migrated_url, backup_dir, DAY, now=now + HOUR) == DAY.total_seconds()
    html = client.get("/settings").text
    assert "Checked:" in html and "Check failed" not in html
    assert sent == ["Backup failed", "Backup works again"]


def test_cut_off_dump_with_older_good_dump_shows_check_failed(pg_tools, migrated_url, sessions, sent, client,
                                                              backup_dir, monkeypatch):
    good = backup.dump(migrated_url, backup_dir, "daily")
    good.rename(backup_dir / f"{OLD_STAMP}-daily.dump")
    real_dump = backup.dump

    def dump(url, d, label):
        p = real_dump(url, d, label)
        data = p.read_bytes()
        p.write_bytes(data[: len(data) // 2])
        return p

    monkeypatch.setattr(backup, "dump", dump)
    now = _now()
    assert backup.daily_step(migrated_url, backup_dir, DAY, now=now) == 3600.0
    html = client.get("/settings").text
    assert "Check failed" in html
    assert "Checked:" not in html
    assert sent == ["Backup failed"]
    assert len(list(backup_dir.glob("*-daily.dump"))) == 1
