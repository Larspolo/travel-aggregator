"""The older trips on the same route and their prices (#1521)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import Capture, Fare, FarePrice, Itinerary, Trip
from app.route_history import RouteTrip, route_history

AT = datetime(2025, 11, 1, 12, tzinfo=UTC)


def _trip(s, origin, destination, day, **kw):
    trip = Trip(title=f"{origin} {destination} {day}", origin_text=origin, destination_text=destination,
                date_from=day, **kw)
    s.add(trip)
    s.flush()
    return trip


def _offer(s, trip, n, prices, travelers, booked=None):
    it = Itinerary(trip=trip, fingerprint=f"fp{trip.id}-{n}", depart_at=AT, arrive_at=AT, duration_min=60)
    fare = Fare(itinerary=it, source="manual", latest_price=Decimal(prices[-1]), currency="EUR", latest_captured_at=AT)
    s.add_all([it, fare])
    s.flush()
    cap = Capture(trip_id=trip.id, source="manual", captured_at=AT, travelers=travelers)
    s.add(cap)
    s.flush()
    for p in prices:
        s.add(FarePrice(fare=fare, price=Decimal(p), currency="EUR", captured_at=AT, capture_id=cap.id))
    if booked:
        it.booked, it.booked_fare_id, it.booked_price, it.booked_currency = True, fare.id, Decimal(booked), "EUR"
    s.flush()


def test_an_older_trip_on_the_same_route_gives_its_cheapest_and_paid_price(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 10), travelers=2)
        old = _trip(s, "amsterdam", "Zurich", date(2025, 12, 12), travelers=2)
        _offer(s, old, 1, ["98.00", "118.00"], 2, booked="118.00")
        s.commit()
        assert route_history(s, trip) == [RouteTrip(old.id, old.title, date(2025, 12, 1), Decimal("49.00"),
                                                    Decimal("59.00"))]


def test_return_split_other_route_and_later_trips_give_no_entry(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 10))
        _trip(s, "Zürich", "Amsterdam", date(2025, 12, 1))
        _trip(s, "Amsterdam", "Zurich", date(2025, 11, 1), split_of_id=trip.id)
        _trip(s, "Amsterdam", "Berlin", date(2025, 10, 1))
        _trip(s, "Amsterdam", "Zurich", date(2027, 1, 1))
        s.commit()
        assert route_history(s, trip) == []


def test_a_trip_with_no_older_trip_gives_nothing(sessions):
    with sessions() as s:
        trip = _trip(s, "Amsterdam", "Zürich", date(2026, 12, 10))
        s.commit()
        assert route_history(s, trip) == []
