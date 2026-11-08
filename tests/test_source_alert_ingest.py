"""An ingest sends "<source>: the last N captures failed" and "<source> works again" (#1173)."""

import pytest

from app import notify
from app.models import Setting
from tests.test_ingest_api import BODY
from tests.test_trip_page import offer, trip  # noqa: F401  (trip is a fixture)

URL = "https://ntfy.example/topic"


@pytest.fixture
def sent(monkeypatch, sessions):
    calls = []
    monkeypatch.setenv("BACKUP_DIR", "/nonexistent-backup-dir")
    monkeypatch.setattr(notify, "post", lambda url, text, headers: calls.append(text))
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value="ntfy"))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value=URL))
        s.commit()
    return calls


def _titles(sent):
    return [text.split("\n")[0] for text in sent]


def _failed(client, auth, trip_id):
    body = {**BODY, "trip_id": trip_id, "raw": "not a bahn.de payload", "offers": []}
    return client.post("/api/ingest", json=body, headers=auth)


def _good(client, auth, trip_id):
    body = {**BODY, "trip_id": trip_id, "offers": [offer("89.90")]}
    return client.post("/api/ingest", json=body, headers=auth)


def test_two_failed_captures_send_one_message(trip, sent):  # noqa: F811
    client, auth, tid = trip
    first = _failed(client, auth, tid)
    assert first.status_code == 200
    assert sent == []
    second = _failed(client, auth, tid)
    assert second.status_code == 200
    assert _titles(sent) == ["bahn.de: the last 2 captures failed"]
    third = _failed(client, auth, tid)
    assert third.status_code == 200 and _titles(sent) == ["bahn.de: the last 2 captures failed"]
    assert set(second.json()) == set(first.json())


def test_a_good_capture_after_the_failures_says_it_works_again(trip, sent):  # noqa: F811
    client, auth, tid = trip
    _failed(client, auth, tid)
    _failed(client, auth, tid)
    assert _good(client, auth, tid).status_code == 200
    assert _titles(sent) == ["bahn.de: the last 2 captures failed", "bahn.de works again"]


def test_an_error_in_the_alert_check_does_not_change_the_ingest(trip, sent, monkeypatch):  # noqa: F811
    import app.api.ingest as ingest_api

    def boom(session, base_url):
        raise RuntimeError("check broke")

    monkeypatch.setattr(ingest_api, "source_alert_messages", boom)
    client, auth, tid = trip
    r = _good(client, auth, tid)
    assert r.status_code == 200
    assert r.json()["created"] == 1
    assert sent == []
