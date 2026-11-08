"""The whole backup alert (#1103): each way that the daily backups can stop gives a message to the owner (#1086, #1087,
#1088), and no message holds a secret (P5). Test doubles replace pg_dump and the ntfy POST: no request leaves a test."""

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app import backup, notify
from app.backup import ALERT_KEY, STAMP_FORMAT
from app.models import Setting
from tests.test_trip_page import BODY, offer, trip  # noqa: F401  (trip is a fixture)

NTFY = "https://ntfy.example/topic"
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
DAY = timedelta(hours=24)
PASSWORD = "Pw-7f3a9c-known"
SECRET_KEY = "secret-key-known-41"
SMTP_PASSWORD = "smtp-known-41"


@pytest.fixture
def sent(monkeypatch, sessions, tmp_path):
    """The ntfy channel with a double that keeps (title, text, click) of each message; the known secrets are set."""
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    monkeypatch.setenv("SECRET_KEY", SECRET_KEY)
    monkeypatch.setenv("SMTP_PASSWORD", SMTP_PASSWORD)
    calls = []
    monkeypatch.setattr(notify, "post",
                        lambda url, text, headers: calls.append((headers["Title"], text, headers["Click"])))
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value="ntfy"))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value=NTFY))
        s.commit()
    return calls


def _pg_dump(monkeypatch, code, stderr=""):
    """A double of pg_dump: a good dump writes its file; a failed one gives the exit code and the stderr."""
    def run(args, **kw):
        if code == 0:
            Path(args[args.index("--file") + 1]).write_bytes(b"dump")
        return subprocess.CompletedProcess(args, code, "", stderr)
    monkeypatch.setattr(backup.subprocess, "run", run)


def _titles(sent):
    return [title for title, _, _ in sent]


def _ingest(client, auth, trip_id):
    body = {**BODY, "trip_id": trip_id, "offers": [offer("89.90")]}
    return client.post("/api/ingest", json=body, headers=auth)


def test_failed_dump_sends_one_message_a_day_then_works_again(sent, monkeypatch, tmp_path, migrated_url):
    _pg_dump(monkeypatch, 1, "pg_dump: error: connection to server failed")
    assert backup.daily_step(migrated_url, tmp_path, DAY, now=NOW) == 3600.0
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW + timedelta(hours=1))
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW + timedelta(hours=23))
    assert _titles(sent) == ["Backup failed"]
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW + timedelta(hours=25))
    assert _titles(sent) == ["Backup failed", "Backup failed"]
    _pg_dump(monkeypatch, 0)
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW + timedelta(hours=26))
    assert _titles(sent) == ["Backup failed", "Backup failed", "Backup works again"]
    assert sent[-1][1] == "The daily backup works again."


def test_full_volume_sends_backup_failed(sent, monkeypatch, tmp_path, migrated_url):
    _pg_dump(monkeypatch, 1, "pg_dump: error: could not write to output file: No space left on device")
    with pytest.raises(backup.BackupError, match="No space left on device"):
        backup.dump(migrated_url, tmp_path, "manual")
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW)
    assert _titles(sent) == ["Backup failed"]
    assert "No space left on device" in sent[0][1]


def test_stopped_service_sends_no_backup_message_once_a_day(trip, sent, tmp_path, sessions):  # noqa: F811
    client, auth, tid = trip
    old = datetime.now(UTC) - timedelta(days=4, minutes=5)
    directory = tmp_path / "bk"
    directory.mkdir()
    (directory / f"{old.strftime(STAMP_FORMAT)}-daily.dump").write_bytes(b"x")

    assert _ingest(client, auth, tid).status_code == 200
    assert [(t, x) for t, x, _ in sent] == [("No backup for 4 days", "No backup for 4 days.")]
    assert _ingest(client, auth, tid).status_code == 200
    assert len(sent) == 1

    with sessions() as s:  # the last message is 25 hours old: the next one may go
        s.merge(Setting(key=ALERT_KEY, value=(datetime.now(UTC) - timedelta(hours=25)).isoformat()))
        s.commit()
    assert _ingest(client, auth, tid).status_code == 200
    assert len(sent) == 2


def test_channel_none_sends_no_message(trip, sent, tmp_path, sessions, monkeypatch, migrated_url):  # noqa: F811
    client, auth, tid = trip
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value="none"))
        s.commit()
    _pg_dump(monkeypatch, 1, "pg_dump: error: boom")
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW)
    old = datetime.now(UTC) - timedelta(days=4)
    directory = tmp_path / "bk"
    directory.mkdir(exist_ok=True)
    (directory / f"{old.strftime(STAMP_FORMAT)}-daily.dump").write_bytes(b"x")
    assert _ingest(client, auth, tid).status_code == 200
    assert sent == []


def test_no_message_holds_a_password_a_secret_or_a_token(trip, sent, tmp_path, sessions, monkeypatch,  # noqa: F811
                                                         migrated_url):
    client, auth, tid = trip
    # The test database uses trust authentication: the password in the URL is known to the app, not checked.
    db_url = migrated_url.replace("postgres@", f"postgres:{PASSWORD}@", 1)
    assert PASSWORD in db_url
    known = [PASSWORD, SECRET_KEY, SMTP_PASSWORD, auth["Authorization"].split(" ", 1)[1], db_url]

    _pg_dump(monkeypatch, 1, f"pg_dump: error: connection to {db_url} failed: password {PASSWORD} rejected")
    backup.daily_step(db_url, tmp_path, DAY, now=NOW)
    _pg_dump(monkeypatch, 0)
    backup.daily_step(db_url, tmp_path, DAY, now=NOW + timedelta(hours=26))
    old = datetime.now(UTC) - timedelta(days=4)
    directory = tmp_path / "bk"
    directory.mkdir(exist_ok=True)
    (directory / f"{old.strftime(STAMP_FORMAT)}-daily.dump").write_bytes(b"x")
    assert _ingest(client, auth, tid).status_code == 200
    with sessions() as s:
        msgs = notify.alert_messages(s, "Test message from travel-aggregator",
                                     "The channel of travel-aggregator works.", "https://x.example/settings/messages")
        notify.deliver(msgs)

    assert len(sent) == 4
    for title, text, click in sent:
        for value in known:
            assert value and value not in title + text + click, f"{title!r} holds a secret"
