"""The stale sources of a day in the days view (#2114): "search again <source>" with a link, "stale <source>" without."""

import copy
import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.web import pages
from tests.test_trip_day_coverage import _to_berlin
from tests.test_trip_days_strip import _on, _set_range
from tests.test_trip_one_day_cover import _line
from tests.test_trip_page import trip  # noqa: F401  (fixture)
from tests.test_ingest_api import BODY


def _ingest_on_day(client, auth, trip_id, hours_ago, service_no="ICE 1"):
    body = copy.deepcopy(BODY)
    captured = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    body.update(trip_id=trip_id, offers=[_on("2026-05-03", "89.90", service_no)], captured_at=captured.isoformat())
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200


def _setup(sessions, tid):
    _set_range(sessions, tid, date(2026, 5, 3), None)
    _to_berlin(sessions, tid)


def test_a_stale_capture_of_the_day_shows_search_again(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _setup(sessions, tid)
    _ingest_on_day(client, auth, tid, 30)
    line = _line(client.get(f"/trips/{tid}", params={"stale_hours": 24}).text)
    link = re.search(r'<a class="day-stale" href="([^"]+)"[^>]*>search again bahn\.de</a>', line)
    assert link and "hd=2026-05-03" in link.group(1).replace("&amp;", "&")


def test_a_fresh_capture_shows_no_search_again(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _setup(sessions, tid)
    _ingest_on_day(client, auth, tid, 2)
    line = _line(client.get(f"/trips/{tid}", params={"stale_hours": 24}).text)
    assert "search again" not in line


def test_a_longer_stale_hours_removes_the_mark(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _setup(sessions, tid)
    _ingest_on_day(client, auth, tid, 30)
    line = _line(client.get(f"/trips/{tid}", params={"stale_hours": 48}).text)
    assert "search again" not in line and "stale bahn.de" not in line


def test_a_stale_source_without_a_link_shows_stale_only(monkeypatch):
    monkeypatch.setattr("app.search_links.day_links", lambda _trip, day: {"bahn.de": ("DB", "https://x/search")})
    monkeypatch.setattr(pages, "depart_day", lambda it: it.day)
    now = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    old = now - timedelta(hours=30)
    itineraries = [SimpleNamespace(day="2026-05-03", legs=[1], hidden=False, fares=[
        SimpleNamespace(source="ryanair", latest_captured_at=old),
        SimpleNamespace(source="bahn.de", latest_captured_at=old),
    ])]
    a_trip = SimpleNamespace(date_from=date(2026, 5, 3))
    days = [SimpleNamespace(day=date(2026, 5, 3))]
    cover = pages.day_cover(a_trip, itineraries, days, now - timedelta(hours=24))
    names, missing, stale, _closed = cover["2026-05-03"]
    assert ("ryanair", None) in stale
    assert ("DB", "https://x/search") in stale
