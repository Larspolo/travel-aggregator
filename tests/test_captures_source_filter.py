"""The captures page filtered by source (#725): /captures?source=... with and without failed=1."""

import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        trip = Trip(title="Erste Reise")
        s.add(trip)
        s.commit()
        trip_id = trip.id
        s.add_all([
            Capture(trip_id=trip_id, source="bahn.de", captured_at=datetime(2026, 11, 1, tzinfo=timezone.utc)),
            Capture(trip_id=trip_id, source="bahn.de", captured_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
                    unreadable="bahn.de failed capture"),
            Capture(trip_id=trip_id, source="nsinternational.com", captured_at=datetime(2026, 11, 3, tzinfo=timezone.utc)),
            Capture(trip_id=trip_id, source="nsinternational.com", captured_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
                    unreadable="ns failed capture"),
        ])
        s.commit()
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c, "/login")})
    return c


def _csrf(c, path):
    return re.search(r'csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _rows(text, source):
    """The table cells that show the source of a capture."""
    return text.count(f"<td>{source}</td>")


def test_source_filter_lists_only_that_source(client):
    r = client.get("/captures?source=bahn.de")
    assert r.status_code == 200
    assert _rows(r.text, "bahn.de") == 2
    assert _rows(r.text, "nsinternational.com") == 0
    assert "Source: bahn.de" in r.text
    assert 'href="/captures"' in r.text  # the "All sources" link


def test_source_and_failed_filter_lists_only_failed_captures_of_that_source(client):
    r = client.get("/captures?source=bahn.de&failed=1")
    assert r.status_code == 200
    assert _rows(r.text, "bahn.de") == 1
    assert _rows(r.text, "nsinternational.com") == 0
    assert r.text.count('class="chip danger"') == 1
    assert "bahn.de failed capture" in r.text
    assert "ns failed capture" not in r.text


def test_filter_links_keep_the_source(client):
    text = client.get("/captures?source=bahn.de").text
    assert 'href="/captures?failed=1"' not in text
    assert 'href="/captures?source=bahn.de&amp;failed=1"' in text
    text = client.get("/captures?source=bahn.de&failed=1").text
    assert 'href="/captures?source=bahn.de"' in text


def test_unknown_source_gives_the_empty_state(client):
    r = client.get("/captures?source=unknown.example")
    assert r.status_code == 200
    assert _rows(r.text, "bahn.de") == 0
    assert _rows(r.text, "nsinternational.com") == 0
    assert "No captures of this source." in r.text
    assert "<table" not in r.text
