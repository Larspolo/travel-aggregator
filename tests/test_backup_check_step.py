"""The daily backup reads each new dump again; a dump that does not read is a failed backup (#1490)."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app import backup, notify
from app.models import Setting

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
DAY = timedelta(hours=24)


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
def fake_dump(monkeypatch):
    def dump(u, d, kind):
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}-{kind}.dump"
        p.write_bytes(b"dump")
        return p
    monkeypatch.setattr(backup, "dump", dump)


def _check(sessions):
    with sessions() as s:
        return json.loads(s.get(Setting, backup.CHECK_KEY).value)


def test_good_dump_stays_and_stores_its_table_count(migrated_url, sessions, sent, fake_dump, monkeypatch, tmp_path):
    monkeypatch.setattr(backup, "check_dump", lambda p: 7)
    assert backup.daily_step(migrated_url, tmp_path, DAY, now=NOW) == DAY.total_seconds()
    files = list(tmp_path.glob("*-daily.dump"))
    assert len(files) == 1
    check = _check(sessions)
    assert check["file"] == files[0].name and check["tables"] == 7 and "at" in check
    assert sent == []


def test_failed_check_renames_alerts_and_retries(migrated_url, sessions, sent, fake_dump, monkeypatch, tmp_path):
    def bad(p):
        raise backup.BackupError(f"backup check failed: bad file at {migrated_url}")
    monkeypatch.setattr(backup, "check_dump", bad)
    assert backup.daily_step(migrated_url, tmp_path, DAY, now=NOW) == 3600.0
    assert list(tmp_path.glob("*-daily.dump")) == []
    failed = list(tmp_path.glob("*-daily.dump.failed"))
    assert len(failed) == 1
    assert sent == ["Backup failed"]
    check = _check(sessions)
    assert check["file"] + ".failed" == failed[0].name and "bad file" in check["error"]
    assert migrated_url not in check["error"]
    assert backup.newest_backup(tmp_path) is None
    monkeypatch.setattr(backup, "check_dump", lambda p: 3)
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW + timedelta(hours=1))
    assert len(list(tmp_path.glob("*-daily.dump"))) == 1


def test_only_the_newest_failed_file_stays(migrated_url, sent, fake_dump, monkeypatch, tmp_path):
    def bad(p):
        raise backup.BackupError("backup check failed: bad")
    monkeypatch.setattr(backup, "check_dump", bad)
    names = []
    for h in range(3):
        backup.daily_step(migrated_url, tmp_path, DAY, now=NOW + timedelta(hours=h))
        names += [p.name for p in tmp_path.glob("*.failed")]
    assert [p.name for p in tmp_path.glob("*.failed")] == [max(names)]
