"""The days view shows "<source>: sales open on <date>" for a source whose sales of a day are not open yet (#2283)."""

import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.models import Setting
from app.web import pages
from tests.test_trip_one_day_cover import _line
from tests.test_trip_days_strip import _set_range
from tests.test_trip_page import trip  # noqa: F401  (fixture)

TODAY = date(2026, 11, 11)
LINKS = {"bahn.de": ("bahn.de", "https://x/search")}


def _cover(monkeypatch, itineraries=(), horizon=None):
    monkeypatch.setattr("app.search_links.day_links", lambda _trip, day: LINKS)
    monkeypatch.setattr(pages, "depart_day", lambda it: it.day)
    a_trip = SimpleNamespace(date_from=date(2027, 5, 8))
    days = [SimpleNamespace(day=date(2027, 5, d)) for d in range(8, 13)]
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    return pages.day_cover(a_trip, list(itineraries), days, now, TODAY, horizon or {"bahn.de": 180})


def test_each_day_shows_the_date_its_sales_open(monkeypatch):
    cover = _cover(monkeypatch)
    assert cover["2027-05-10"][3] == [("bahn.de", date(2026, 11, 11))]
    assert cover["2027-05-11"][3] == [("bahn.de", date(2026, 11, 12))]
    assert cover["2027-05-12"][3] == [("bahn.de", date(2026, 11, 13))]
    assert cover["2027-05-08"][3] == []
    assert cover["2027-05-09"][3] == []


def test_a_day_with_an_offer_of_the_source_shows_no_mark(monkeypatch):
    offer = SimpleNamespace(day="2027-05-11", legs=[1], hidden=False, fares=[
        SimpleNamespace(source="bahn.de", latest_captured_at=datetime(2026, 11, 1, tzinfo=timezone.utc)),
    ])
    cover = _cover(monkeypatch, [offer])
    assert cover["2027-05-11"][3] == []
    assert cover["2027-05-10"][3] == [("bahn.de", date(2026, 11, 11))]


def test_the_days_view_shows_the_sales_date(trip, sessions):  # noqa: F811
    client, _, tid = trip
    with sessions() as s:
        s.merge(Setting(key="sales_horizon:bahn.de", value="180"))
        s.commit()
    today = datetime.now(timezone.utc).date()
    _set_range(sessions, tid, today + timedelta(days=200), None)
    line = _line(client.get(f"/trips/{tid}").text)
    mark = re.search(r'<span class="day-sales-closed">bahn\.de: sales open on ([0-9-]+)</span>', line)
    assert mark and mark.group(1) == (today + timedelta(days=20)).isoformat()
