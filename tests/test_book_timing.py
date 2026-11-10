"""The lowest captured price per step of days before the departure (#1915)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

from app.book_timing import Step, book_timing
from app.models import Capture, Fare, FarePrice, Itinerary, Trip

DEPART = datetime(2026, 12, 10, 8, tzinfo=UTC)


def _trip(s):
    trip = Trip(title="Amsterdam Zürich", origin_text="Amsterdam", destination_text="Zürich", date_from=date(2026, 12, 10))
    s.add(trip)
    s.flush()
    return trip


def _offer(s, trip, prices, currency="EUR", hidden=False, travelers=None):
    """prices: (days before the departure, price) of one fare."""
    it = Itinerary(trip=trip, fingerprint=uuid.uuid4().hex, depart_at=DEPART, arrive_at=DEPART,
                   duration_min=60, hidden=hidden)
    fare = Fare(itinerary=it, source="manual", latest_price=D(prices[-1][1]), currency=currency,
                latest_captured_at=DEPART)
    s.add_all([it, fare])
    s.flush()
    for days, price in prices:
        at = DEPART - timedelta(days=days)
        cap = Capture(trip_id=trip.id, source="manual", captured_at=at, travelers=travelers)
        s.add(cap)
        s.flush()
        s.add(FarePrice(fare=fare, price=D(price), currency=currency, captured_at=at, capture_id=cap.id))
    s.flush()


def test_each_step_with_a_capture_gives_its_lowest_price(sessions):
    with sessions() as s:
        trip = _trip(s)
        _offer(s, trip, [(3, "50.00"), (20, "40.00"), (100, "30.00")])
        _offer(s, trip, [(2, "45.00"), (25, "60.00")])
        assert book_timing(s, [trip.id]) == [Step(0, 7, D("45.00")), Step(15, 30, D("40.00")),
                                             Step(91, None, D("30.00"))]


def test_the_limits_of_each_step(sessions):
    with sessions() as s:
        trip = _trip(s)
        _offer(s, trip, [(0, "10.00"), (7, "11.00"), (8, "12.00"), (14, "13.00"), (15, "14.00"), (30, "15.00"),
                         (31, "16.00"), (60, "17.00"), (61, "18.00"), (90, "19.00"), (91, "20.00")])
        assert book_timing(s, [trip.id]) == [Step(0, 7, D("10.00")), Step(8, 14, D("12.00")), Step(15, 30, D("14.00")),
                                             Step(31, 60, D("16.00")), Step(61, 90, D("18.00")),
                                             Step(91, None, D("20.00"))]
        trip2 = _trip(s)
        _offer(s, trip2, [(7, "11.00"), (14, "13.00"), (30, "15.00"), (60, "17.00"), (90, "19.00")])
        assert [st.lowest_eur for st in book_timing(s, [trip2.id])] == [D("11.00"), D("13.00"), D("15.00"),
                                                                        D("17.00"), D("19.00")]


def test_hidden_no_rate_after_the_departure_and_no_capture_do_not_count(sessions):
    with sessions() as s:
        trip = _trip(s)
        _offer(s, trip, [(3, "5.00")], hidden=True)
        _offer(s, trip, [(3, "6.00")], currency="XYZ")
        _offer(s, trip, [(-1, "7.00")])
        _offer(s, trip, [(3, "80.00")])
        assert book_timing(s, [trip.id]) == [Step(0, 7, D("80.00"))]
        assert book_timing(s, [_trip(s).id]) == []
        assert book_timing(s, []) == []


def test_a_group_price_is_per_traveler_and_two_trips_count_together(sessions):
    with sessions() as s:
        trip, old = _trip(s), _trip(s)
        _offer(s, trip, [(3, "100.00")], travelers=2)   # a manual offer gives the price of all travelers
        _offer(s, old, [(3, "49.99")])
        assert book_timing(s, [trip.id]) == [Step(0, 7, D("50.00"))]
        assert book_timing(s, [trip.id, old.id]) == [Step(0, 7, D("49.99"))]
