"""Per-source metrics of GET /metrics: captures, failed captures and the age of the last good capture (#1893)."""

import re
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models import Capture, Trip
from tests.test_upcoming_page import client  # noqa: F401  (client is a fixture)


def _csrf(c) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get("/settings").text).group(1)


def _new_token(c) -> str:
    r = c.post("/settings/metrics-token", data={"csrf_token": _csrf(c)})
    return re.search(r'value="([^"]+)" aria-label="Metrics token"', r.text).group(1)


def _lines(token) -> list[str]:
    r = TestClient(app).get("/metrics", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return r.text.splitlines()


def _cap(trip_id, source, captured_at, ok=True):
    return Capture(trip_id=trip_id, source=source, parser_version="1.0.0", captured_at=captured_at,
                   offer_count=3 if ok else None, rejected_count=0,
                   unreadable=None if ok else "no JSON")


def _add(sessions, captures):
    with sessions() as s:
        trip = Trip(title="Reise")
        s.add(trip)
        s.flush()
        s.add_all([_cap(trip.id, *c) for c in captures])
        s.commit()


def test_three_bahn_captures_one_unreadable_gives_total_and_failures(client, sessions):  # noqa: F811
    now = datetime.now(UTC)
    _add(sessions, [
        ("bahn.de", now - timedelta(hours=3), True),
        ("bahn.de", now - timedelta(hours=2), False),
        ("bahn.de", now - timedelta(hours=1), True),
    ])
    lines = _lines(_new_token(client))
    assert 'travel_captures_total{source="bahn.de"} 3' in lines
    assert 'travel_capture_failures_total{source="bahn.de"} 1' in lines
    assert "# TYPE travel_captures_total counter" in lines
    assert "# TYPE travel_capture_failures_total counter" in lines
    assert "# TYPE travel_last_good_capture_age_seconds gauge" in lines


def test_age_of_last_good_capture_is_seconds_since_it(client, sessions):  # noqa: F811
    _add(sessions, [("bahn.de", datetime.now(UTC) - timedelta(seconds=3600), True)])
    lines = _lines(_new_token(client))
    age_lines = [x for x in lines if x.startswith('travel_last_good_capture_age_seconds{source="bahn.de"} ')]
    assert len(age_lines) == 1
    age = float(age_lines[0].rsplit(" ", 1)[1])
    assert 3600 <= age <= 3660


def test_source_without_good_capture_has_no_age_line(client, sessions):  # noqa: F811
    _add(sessions, [("flixbus", datetime.now(UTC) - timedelta(hours=1), False)])
    lines = _lines(_new_token(client))
    assert 'travel_captures_total{source="flixbus"} 1' in lines
    assert 'travel_capture_failures_total{source="flixbus"} 1' in lines
    assert not any(x.startswith('travel_last_good_capture_age_seconds{source="flixbus"}') for x in lines)


def test_quote_in_source_name_is_escaped(client, sessions):  # noqa: F811
    _add(sessions, [('a"b', datetime.now(UTC) - timedelta(hours=1), True)])
    lines = _lines(_new_token(client))
    assert 'travel_captures_total{source="a\\"b"} 1' in lines


def test_backslash_and_line_break_in_source_name_are_escaped(client, sessions):  # noqa: F811
    _add(sessions, [("a\\b\nc", datetime.now(UTC) - timedelta(hours=1), True)])
    assert 'travel_captures_total{source="a\\\\b\\nc"} 1' in _lines(_new_token(client))
