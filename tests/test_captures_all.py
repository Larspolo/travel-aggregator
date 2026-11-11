"""The captures of all trips on one page (#347)."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Trip

FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen-bahncard25.json"
PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        token = tokens.create(s, "test")
        first = Trip(title="Erste Reise")
        second = Trip(title="Zweite Reise")
        s.add_all([first, second])
        s.commit()
        ids = (first.id, second.id)
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c, "/login")})
    return c, {"Authorization": f"Bearer {token}"}, ids


def _csrf(c, path):
    return re.search(r'csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _ingest(c, auth, trip_id, captured_at):
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    r = c.post("/api/ingest", headers=auth, json={"trip_id": trip_id, "source": "bahn.de", "parser_version": "0.0.1",
                                                  "captured_at": captured_at, "raw": raw})
    assert r.status_code < 300, r.text


def test_captures_page_lists_all_trips_newest_first_with_links(client):
    c, auth, (first, second) = client
    _ingest(c, auth, first, "2026-11-01T10:00:00Z")
    _ingest(c, auth, second, "2026-11-03T10:00:00Z")
    r = c.get("/captures")
    assert r.status_code == 200
    text = r.text
    assert "Captures of all trips" in text
    assert "Back to the trip" not in text
    assert f'href="/trips/{first}"' in text and f'href="/trips/{second}"' in text
    assert "Erste Reise" in text and "Zweite Reise" in text
    assert text.index("Zweite Reise") < text.index("Erste Reise")


def test_captures_page_needs_a_login(sessions):
    r = TestClient(app, follow_redirects=False).get("/captures")
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=%2Fcaptures"  # the target of #2103


def test_nav_of_a_page_has_the_captures_link(client):
    c, _, (first, _) = client
    assert 'href="/captures"' in c.get("/settings").text
    assert 'href="/captures"' in c.get(f"/trips/{first}").text
