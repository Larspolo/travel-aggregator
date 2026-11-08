"""An ingest sends "No backup for N days" when the newest backup is old (#1088), at most once in 24 hours."""

from datetime import UTC, datetime, timedelta

import pytest

from app import notify
from app.backup import STAMP_FORMAT
from app.models import Setting
from tests.test_trip_page import BODY, offer, trip  # noqa: F401  (trip is a fixture)

URL = "https://ntfy.example/topic"


@pytest.fixture
def sent(monkeypatch, tmp_path, sessions):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    calls = []
    monkeypatch.setattr(notify, "post", lambda url, text, headers: calls.append(text))
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value="ntfy"))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value=URL))
        s.commit()
    return calls


def _write(directory, when):
    directory.mkdir(exist_ok=True)
    (directory / f"{when.strftime(STAMP_FORMAT)}-daily.dump").write_bytes(b"x")


def _ingest(client, auth, trip_id):
    body = {**BODY, "trip_id": trip_id, "offers": [offer("89.90")]}
    return client.post("/api/ingest", json=body, headers=auth)


def test_an_old_backup_sends_one_message(trip, sent, tmp_path):  # noqa: F811
    client, auth, tid = trip
    _write(tmp_path / "bk", datetime.now(UTC) - timedelta(days=3, minutes=5))
    r = _ingest(client, auth, tid)
    assert r.status_code == 200
    assert sent == ["No backup for 3 days."]
    second = _ingest(client, auth, tid)
    assert second.status_code == 200 and sent == ["No backup for 3 days."]
    assert set(second.json()) == set(r.json())


def test_a_new_backup_sends_no_message(trip, sent, tmp_path):  # noqa: F811
    client, auth, tid = trip
    _write(tmp_path / "bk", datetime.now(UTC) - timedelta(hours=2))
    assert _ingest(client, auth, tid).status_code == 200
    assert sent == []


def test_no_backup_with_trips_sends_a_message(trip, sent, tmp_path):  # noqa: F811
    client, auth, tid = trip
    (tmp_path / "bk").mkdir()
    assert _ingest(client, auth, tid).status_code == 200
    assert sent == ["No backup yet."]


def test_a_missing_backup_directory_sends_no_message(trip, sent):  # noqa: F811
    client, auth, tid = trip
    assert _ingest(client, auth, tid).status_code == 200
    assert sent == []
