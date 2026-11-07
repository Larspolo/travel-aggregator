"""The status per source on the captures page (#724)."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip
from app.sourcehealth import source_health

PASSWORD = "pw"
T0 = datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc)


def _cap(trip_id, source, hours, version, ok):
    return Capture(trip_id=trip_id, source=source, parser_version=version, captured_at=T0 + timedelta(hours=hours),
                   offer_count=3 if ok else 0, rejected_count=0, unreadable=None if ok else "no JSON")


@pytest.fixture
def seeded(sessions):
    with sessions() as s:
        trip = Trip(title="Reise")
        s.add(trip)
        s.flush()
        s.add_all([_cap(trip.id, "bahn.de", 0, "1.0.0", True), _cap(trip.id, "bahn.de", 1, "1.1.0", True),
                   _cap(trip.id, "bahn.de", 2, "1.1.0", False), _cap(trip.id, "bahn.de", 3, "1.1.0", False),
                   _cap(trip.id, "flixbus.de", 1, "0.1.0", False)])
        s.commit()
    return sessions


def test_source_health_counts_the_failed_captures_after_the_last_good_one(seeded):
    with seeded() as s:
        health = {h["source"]: h for h in source_health(s)}
    bahn = health["bahn.de"]
    assert bahn["failed_after"] == 2
    assert bahn["parser_version"] == "1.1.0"
    assert bahn["last_good_at"] == T0 + timedelta(hours=1)
    assert bahn["last_at"] == T0 + timedelta(hours=3)
    assert health["flixbus.de"]["last_good_at"] is None
    assert health["flixbus.de"]["failed_after"] == 1


def test_captures_page_shows_the_sources_table(seeded, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    html = c.get("/captures").text
    table = html[html.index('id="source-health"'):]
    table = table[:table.index("</section>")]
    rows = re.findall(r"<tr class=\"source-row\"><td>(.*?)</tr>", table, re.S)
    assert rows[0].startswith("bahn.de") and "1.1.0" in rows[0] and ">2<" in rows[0]
    assert '2026-11-01T09:00:00+00:00' in rows[0]
    assert rows[1].startswith("flixbus.de") and "never" in rows[1]
    trip_page = c.get("/trips/1/captures").text
    assert 'id="source-health"' not in trip_page
