"""The captures page counts the fares with the mark "check the price" for each capture (#1607)."""

from datetime import UTC, datetime
from decimal import Decimal

from app.models import Capture, Fare, FarePrice, Itinerary
from app.suspect import suspect_counts
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _day(n):
    return datetime(2026, 11, n, 12, tzinfo=UTC)


def _capture(s, trip_id, n, offers=1):
    cap = Capture(trip_id=trip_id, source="bahn", captured_at=_day(n), travelers=1)
    cap.offer_count = offers
    s.add(cap)
    s.flush()
    return cap


def _fare(s, trip_id, rows, n=1):
    """A fare with one price row per (day, price, capture) in `rows`; the last row is the latest price."""
    it = Itinerary(trip_id=trip_id, fingerprint=f"suspect-{trip_id}-{n}", depart_at=_day(1), arrive_at=_day(1),
                   duration_min=60)
    s.add(it)
    s.flush()
    day, price, cap = rows[-1]
    fare = Fare(itinerary=it, source="bahn", latest_price=Decimal(price), currency="EUR", latest_captured_at=_day(day))
    s.add(fare)
    s.flush()
    for d, p, c in rows:
        s.add(FarePrice(fare=fare, price=Decimal(p), currency="EUR", captured_at=_day(d), capture_id=c.id))
    s.flush()
    return fare


def test_the_capture_that_gave_the_implausible_price_counts_it(sessions, trip):  # noqa: F811
    _, _, trip_id = trip
    with sessions() as s:
        first = _capture(s, trip_id, 1)
        second = _capture(s, trip_id, 2)
        plausible = _capture(s, trip_id, 3)
        _fare(s, trip_id, [(1, "39.00", first), (2, "3.50", second)], n=1)
        _fare(s, trip_id, [(1, "39.00", first), (3, "41.00", plausible)], n=2)
        s.commit()
        counts = suspect_counts(s, [trip_id])
        assert counts.get(second.id) == 1
        assert first.id not in counts
        assert plausible.id not in counts


def test_a_capture_with_no_offer_has_no_count(sessions, trip):  # noqa: F811
    _, _, trip_id = trip
    with sessions() as s:
        empty = _capture(s, trip_id, 1, offers=None)
        s.commit()
        assert empty.id not in suspect_counts(s, [trip_id])


def test_the_count_appears_on_the_trip_and_the_all_captures_page(sessions, trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    with sessions() as s:
        first = _capture(s, trip_id, 1)
        second = _capture(s, trip_id, 2)
        _fare(s, trip_id, [(1, "39.00", first), (2, "0", second)], n=1)
        s.commit()
    for url in (f"/trips/{trip_id}/captures", "/captures"):
        page = client.get(url).text
        assert "<th>Check the price</th>" in page
        assert '<span class="warn">1</span>' in page
