"""A message when the daily backup fails, and when it works again (#1087). Test doubles replace the dump and the POST."""

from datetime import UTC, datetime, timedelta

import pytest

from app import backup, notify
from app.models import Setting

URL = "https://ntfy.example/topic"
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
DAY = timedelta(hours=24)


@pytest.fixture
def sent(monkeypatch, sessions):
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value="ntfy"))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value=URL))
        s.commit()
    calls = []
    monkeypatch.setattr(notify, "post", lambda url, text, headers: calls.append((headers["Title"], text)))
    return calls


def _fail(monkeypatch, url):
    def dump(u, d, kind):
        raise backup.BackupError(f"pg_dump: connection to {u} failed: no_such_host")
    monkeypatch.setattr(backup, "dump", dump)


def _work(monkeypatch):
    monkeypatch.setattr(backup, "dump", lambda u, d, kind: d / "x-daily.dump")
    monkeypatch.setattr(backup, "_check_step", lambda u, path, now: None)


def test_failures_send_one_message_a_day(migrated_url, sent, monkeypatch, tmp_path):
    _fail(monkeypatch, migrated_url)
    for h in range(3):
        assert backup.daily_step(migrated_url, tmp_path, DAY, now=NOW + timedelta(hours=h)) == 3600.0
    assert len(sent) == 1
    title, text = sent[0]
    assert title == "Backup failed" and "no_such_host" in text
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW + timedelta(hours=25))
    assert len(sent) == 2


def test_first_good_dump_sends_works_again_once(migrated_url, sent, monkeypatch, tmp_path):
    _fail(monkeypatch, migrated_url)
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW)
    _work(monkeypatch)
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW + timedelta(hours=1))
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW + timedelta(hours=2))
    assert [t for t, _ in sent] == ["Backup failed", "Backup works again"]


def test_message_holds_no_database_url_or_password(migrated_url, sent, monkeypatch, tmp_path):
    from sqlalchemy.engine import make_url

    _fail(monkeypatch, migrated_url)
    backup.daily_step(migrated_url, tmp_path, DAY, now=NOW)
    text = sent[0][1]
    assert migrated_url not in text
    password = make_url(backup.sqlalchemy_url(migrated_url)).password
    if password:
        assert password not in text


def test_secret_password_is_removed():
    url = "postgresql://app:s3cret@db:5432/app"
    assert "s3cret" not in backup._redact("x postgresql://app:s3cret@db/other s3cret", url)


def test_a_failed_send_still_returns_the_retry_delay(migrated_url, sent, monkeypatch, tmp_path):
    def boom(msgs, new_session=None):
        raise RuntimeError("send failed")
    monkeypatch.setattr(notify, "deliver", boom)
    _fail(monkeypatch, migrated_url)
    assert backup.daily_step(migrated_url, tmp_path, DAY, now=NOW) == 3600.0
