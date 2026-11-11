"""The "Changes" column of the captures page: what each capture showed new, lower or higher (#2328)."""

import re
from datetime import UTC, datetime
from decimal import Decimal

from app.capture_changes import capture_changes
from app.models import Capture, Fare, FarePrice, Itinerary
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _day(n):
    return datetime(2026, 11, n, 12, tzinfo=UTC)


def _capture(s, trip_id, n, offers=1):
    cap = Capture(trip_id=trip_id, source="bahn", captured_at=_day(n), travelers=1)
    cap.offer_count = offers
    s.add(cap)
    s.flush()
    return cap


def _itinerary(s, trip_id, name):
    it = Itinerary(trip_id=trip_id, fingerprint=f"changes-{trip_id}-{name}", depart_at=_day(1), arrive_at=_day(1),
                   duration_min=60)
    s.add(it)
    s.flush()
    return it


def _fare(s, it, rows, currency="EUR"):
    """A fare of the itinerary with one price row per (day, price, capture) in `rows`, oldest first."""
    day, price, _ = rows[-1]
    fare = Fare(itinerary=it, source="bahn", latest_price=Decimal(price), currency=currency,
                latest_captured_at=_day(day))
    s.add(fare)
    s.flush()
    for d, p, c in rows:
        s.add(FarePrice(fare=fare, price=Decimal(p), currency=currency, captured_at=_day(d), capture_id=c.id))
    s.flush()
    return fare


def _berlin_day(s, trip_id, first, second, third):
    """ICE 105 falls from 89 to 79, ICE 145 stays at 89.90, IC 2021 is new at 45 in the second capture."""
    ice105 = _itinerary(s, trip_id, "ice105")
    ice145 = _itinerary(s, trip_id, "ice145")
    ic2021 = _itinerary(s, trip_id, "ic2021")
    _fare(s, ice105, [(1, "89.00", first), (2, "79.00", second), (3, "79.00", third)])
    _fare(s, ice145, [(1, "89.90", first), (2, "89.90", second), (3, "89.90", third)])
    _fare(s, ic2021, [(2, "45.00", second), (3, "45.00", third)])
    return ice105, ice145, ic2021


def test_a_new_itinerary_and_a_lower_price_are_counted_on_the_capture(sessions, trip):  # noqa: F811
    _, _, trip_id = trip
    with sessions() as s:
        first = _capture(s, trip_id, 1)
        second = _capture(s, trip_id, 2)
        third = _capture(s, trip_id, 3)
        ice105, ice145, ic2021 = _berlin_day(s, trip_id, first, second, third)
        s.commit()
        changes = capture_changes(s, [second.id, third.id])
        assert changes[second.id].new == {ic2021.id}
        assert changes[second.id].lower == {ice105.id}
        assert changes[second.id].higher == set()
        assert ice145.id not in changes[second.id].lower
        assert changes[third.id].new == set()
        assert changes[third.id].lower == set()
        assert changes[third.id].higher == set()


def test_a_higher_price_is_counted_as_higher(sessions, trip):  # noqa: F811
    _, _, trip_id = trip
    with sessions() as s:
        first = _capture(s, trip_id, 1)
        second = _capture(s, trip_id, 2)
        it = _itinerary(s, trip_id, "up")
        _fare(s, it, [(1, "40.00", first), (2, "55.00", second)])
        s.commit()
        assert capture_changes(s, [second.id])[second.id].higher == {it.id}


def test_a_price_in_another_currency_is_no_change(sessions, trip):  # noqa: F811
    _, _, trip_id = trip
    with sessions() as s:
        first = _capture(s, trip_id, 1)
        second = _capture(s, trip_id, 2)
        it = _itinerary(s, trip_id, "usd")
        _fare(s, it, [(1, "50.00", first), (2, "40.00", second)], currency="EUR")
        s.query(FarePrice).filter(FarePrice.capture_id == second.id).update({"currency": "USD"})
        s.commit()
        changes = capture_changes(s, [second.id])[second.id]
        assert changes.lower == set()
        assert changes.higher == set()
        assert changes.new == set()


def test_a_capture_with_no_offer_has_no_change(sessions, trip):  # noqa: F811
    _, _, trip_id = trip
    with sessions() as s:
        empty = _capture(s, trip_id, 1, offers=None)
        s.commit()
        changes = capture_changes(s, [empty.id])[empty.id]
        assert not (changes.new or changes.lower or changes.higher)


def test_the_changes_appear_on_the_trip_and_the_all_captures_page(sessions, trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    with sessions() as s:
        first = _capture(s, trip_id, 1)
        second = _capture(s, trip_id, 2)
        third = _capture(s, trip_id, 3)
        _berlin_day(s, trip_id, first, second, third)
        s.commit()
    for url in (f"/trips/{trip_id}/captures", "/captures"):
        page = client.get(url).text
        assert "<th>Changes</th>" in page
        assert "1 new, 1 lower, 0 higher" in re.sub(r"<[^>]+>", "", page)  # the counts are links (#2329)
        assert "no change" in page
