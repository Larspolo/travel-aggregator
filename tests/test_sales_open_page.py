"""The search status shows "sales open on <date>" with no link before the sales of a source open (#2254)."""

import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.coverage import trip_coverage
from app.sales_open import horizons
from app.models import Setting, Trip
from app.web import pages
from tests.test_trip_days_strip import _set_range
from tests.test_trip_page import trip  # noqa: F401  (fixture)

TODAY = date(2026, 11, 11)


def _horizon(sessions, days="180"):
    with sessions() as s:
        s.merge(Setting(key="sales_horizon:bahn.de", value=days))
        s.commit()


def _bahn(sessions, tid, today=TODAY):
    with sessions() as s:
        return next(c for c in trip_coverage(s, s.get(Trip, tid), today, horizons(s)) if c["source"] == "bahn.de")


def test_a_trip_after_the_horizon_shows_the_sales_date(trip, sessions):  # noqa: F811
    _, _, tid = trip
    _horizon(sessions)
    _set_range(sessions, tid, date(2027, 6, 1), None)
    assert _bahn(sessions, tid)["sales_open_on"] == date(2026, 12, 3)


def test_a_trip_in_the_horizon_and_no_horizon_keep_the_status(trip, sessions):  # noqa: F811
    _, _, tid = trip
    _set_range(sessions, tid, date(2027, 6, 1), None)
    assert _bahn(sessions, tid)["sales_open_on"] is None
    _horizon(sessions)
    _set_range(sessions, tid, date(2027, 3, 1), None)
    assert _bahn(sessions, tid)["sales_open_on"] is None


def test_the_page_shows_the_date_with_no_link(trip, sessions):  # noqa: F811
    client, _, tid = trip
    _horizon(sessions)
    today = datetime.now(timezone.utc).date()
    _set_range(sessions, tid, today + timedelta(days=200), None)
    html = client.get(f"/trips/{tid}").text
    status = re.search(r'<ul class="search-links".*?</ul>', html, re.S).group(0)
    item = re.search(r"<li>[^<]*: sales open on [^<]*</li>", status)
    assert item and (today + timedelta(days=20)).isoformat() in item.group(0)
    _set_range(sessions, tid, today + timedelta(days=100), None)
    status = re.search(r'<ul class="search-links".*?</ul>', client.get(f"/trips/{tid}").text, re.S).group(0)
    assert "sales open on" not in status and "not searched yet" in status


def test_the_days_view_marks_only_the_days_after_the_horizon(monkeypatch):
    monkeypatch.setattr("app.search_links.day_links", lambda _trip, day: {"bahn.de": ("bahn.de", "https://x/search")})
    a_trip = SimpleNamespace(date_from=date(2027, 5, 8))
    days = [SimpleNamespace(day=date(2027, 5, d)) for d in range(8, 13)]
    cover = pages.day_cover(a_trip, [], days, datetime(2026, 11, 1, tzinfo=timezone.utc), TODAY, {"bahn.de": 180})
    marked = [key[-2:] for key, entry in cover.items() if entry[3] == ["bahn.de"]]
    assert marked == ["10", "11", "12"]
    assert all(entry[1] == [] for key, entry in cover.items() if key[-2:] in marked)
    assert cover["2027-05-08"][1] == [("bahn.de", "https://x/search")]
