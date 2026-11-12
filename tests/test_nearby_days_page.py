"""The cheaper days next to a trip on its page, and "Add this day" (#2525)."""

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.models import DayPrice, Trip
from app.nearby_days import add_day_span
from tests.test_trip_days_strip import _on, _set_range
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)


def _price(sessions, tid, day, amount):
    with sessions() as s:
        s.add(DayPrice(source="bahn.de", trip_id=tid, day=day, price=Decimal(amount), currency="EUR",
                       captured_at=datetime.now(timezone.utc)))
        s.commit()


def _csrf(client, tid):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{tid}").text).group(1)


def _nearby(html):
    m = re.search(r'<ul id="nearby-days".*?</ul>', html, re.S)
    return m.group(0) if m else ""


# The span is 40 days from today, so the cheaper days are never in the past (#2541).
D = date.today() + timedelta(days=40)


def _setup(sessions, client, auth, tid):
    _set_range(sessions, tid, D, D)
    ingest(client, auth, tid, [_on(D.isoformat(), "49.00", "ICE 1")])
    _price(sessions, tid, D - timedelta(days=1), "29.00")
    _price(sessions, tid, D + timedelta(days=1), "59.00")


def test_page_shows_the_cheaper_day_only(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _setup(sessions, client, auth, tid)
    nearby = _nearby(client.get(f"/trips/{tid}").text)
    before = D - timedelta(days=1)
    assert f"{before:%a %d %b}: from €29.00 (bahn.de day price), €20.00 less" in nearby
    assert f"{D + timedelta(days=1):%a %d %b}" not in nearby  # 59 is not cheaper than the trip


def test_add_this_day_before_the_span_moves_the_first_date(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _setup(sessions, client, auth, tid)
    r = client.post(f"/trips/{tid}/add-day",
                    data={"csrf_token": _csrf(client, tid), "day": (D - timedelta(days=1)).isoformat()},
                    follow_redirects=False)
    assert r.status_code == 303
    with sessions() as s:
        t = s.get(Trip, tid)
        assert (t.date_from, t.date_to) == (D - timedelta(days=1), D)


def test_add_this_day_after_the_span_moves_the_last_date(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _setup(sessions, client, auth, tid)
    r = client.post(f"/trips/{tid}/add-day",
                    data={"csrf_token": _csrf(client, tid), "day": (D + timedelta(days=2)).isoformat()},
                    follow_redirects=False)
    assert r.status_code == 303
    with sessions() as s:
        t = s.get(Trip, tid)
        assert (t.date_from, t.date_to) == (D, D + timedelta(days=2))


def test_a_day_five_out_of_the_span_gives_400_and_no_change(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _setup(sessions, client, auth, tid)
    r = client.post(f"/trips/{tid}/add-day",
                    data={"csrf_token": _csrf(client, tid), "day": (D - timedelta(days=5)).isoformat()},
                    follow_redirects=False)
    assert r.status_code == 400
    with sessions() as s:
        t = s.get(Trip, tid)
        assert (t.date_from, t.date_to) == (D, D)


def test_post_without_csrf_token_changes_nothing(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _setup(sessions, client, auth, tid)
    r = client.post(f"/trips/{tid}/add-day", data={"day": (D - timedelta(days=1)).isoformat()},
                    follow_redirects=False)
    assert r.status_code == 403
    with sessions() as s:
        t = s.get(Trip, tid)
        assert (t.date_from, t.date_to) == (D, D)


def test_trip_with_no_day_prices_shows_no_list(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _set_range(sessions, tid, D, D)
    ingest(client, auth, tid, [_on(D.isoformat(), "49.00", "ICE 1")])
    assert _nearby(client.get(f"/trips/{tid}").text) == ""


def test_add_day_span_pure_rules():
    d = D
    one, three = timedelta(days=1), timedelta(days=3)
    assert add_day_span(d, None, d - one) == (d - one, d)
    assert add_day_span(d, d, d + three) == (d, d + three)
