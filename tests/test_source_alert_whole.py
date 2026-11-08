"""The message of a failing source works for each source of the app: from the ingest request to the message (#1175).

The sender is a double (`notify.post`), so no request leaves the test (P1). Each source gets two unreadable captures,
one more unreadable capture (no new message), and one good capture (the message "works again")."""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import pytest

from app import notify
from app.models import Setting
from app.parsers import all_sources
from tests.test_ingest_api import BODY
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

FIXTURES = Path(__file__).parent / "fixtures"
T0 = datetime(2026, 11, 3, 8, 0, tzinfo=UTC)
BASE = "http://testserver"


@pytest.fixture
def sent(monkeypatch, sessions):
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value="ntfy"))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value="https://ntfy.example/topic"))
        s.commit()
    calls = []
    monkeypatch.setattr(notify, "post", lambda url, text, headers: calls.append((headers["Title"], text)))
    return calls


def _good_raw(source):
    """The trimmed fixture of the source: the first JSON file of its directory (sorted by name)."""
    path = sorted((FIXTURES / source).glob("*.json"))[0]
    return json.loads(path.read_text(encoding="utf-8"))


def _post(client, auth, trip_id, source, hour, raw):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, source=source, parser_version="1.0.0",
                captured_at=(T0 + timedelta(hours=hour)).isoformat(), offers=[], raw=raw)
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200
    return r.json()


@pytest.mark.parametrize("source", all_sources())
def test_failing_source_messages_for_each_source(trip, sent, source):  # noqa: F811
    client, auth, tid = trip
    unreadable = {"not": "a payload of this source"}
    link = f"{BASE}/captures?{urlencode({'failed': 1, 'source': source})}"

    _post(client, auth, tid, source, 0, unreadable)
    _post(client, auth, tid, source, 1, unreadable)
    failed = [t for t, _ in sent]
    assert failed == [f"{source}: the last 2 captures failed"]
    assert link in sent[0][1]

    _post(client, auth, tid, source, 2, unreadable)
    assert [t for t, _ in sent] == failed

    assert _post(client, auth, tid, source, 3, _good_raw(source))["rejected"] == 0
    assert [t for t, _ in sent][1:] == [f"{source} works again"]

    assert _post(client, auth, tid, source, 4, _good_raw(source))["rejected"] == 0
    assert [t for t, _ in sent][1:] == [f"{source} works again"]
