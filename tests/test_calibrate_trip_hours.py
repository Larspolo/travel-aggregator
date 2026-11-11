"""A booking on a trip with its own hour value does not tell the hour value of the profile (#2426, epic #1708)."""

import dataclasses
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.calibrate import booking_intervals
from app.models import Fare, FarePrice, Itinerary, Leg, Trip
from app.ranking import Weights

D = Decimal
BOOKED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
DEPART = BOOKED_AT + timedelta(days=10)
WEIGHTS = dataclasses.replace(Weights(), hour_markup=D("10"))


def _it(name, hours, prices, depart=DEPART, **marks):
    """An itinerary with one fare and its price history: (price, captured_at) pairs."""
    arrive = depart + timedelta(hours=hours)
    leg = Leg(seq=0, mode="train", carrier="NS", service_no=name, from_name="A", to_name="B", depart_at=depart,
              depart_offset_min=60, arrive_at=arrive, arrive_offset_min=60)
    history = [FarePrice(price=D(p), currency="EUR", captured_at=at) for p, at in prices]
    last = max(prices, key=lambda pa: pa[1])
    fare = Fare(source="manual", latest_price=D(last[0]), currency="EUR", latest_captured_at=last[1], prices=history)
    return Itinerary(fingerprint=name, depart_at=depart, arrive_at=arrive, duration_min=hours * 60, legs=[leg],
                     fares=[fare], **marks)


def _booked(name="booked", hours=2, price="120", **marks):
    marks = {"booked": True, "booked_at": BOOKED_AT, **marks}
    return _it(name, hours, [(price, BOOKED_AT - timedelta(hours=1))], **marks)


def _trip(sessions, *its, hour_value=None):
    trip = Trip(title="T", origin_text="A", destination_text="B", status="planning", date_from=DEPART.date(),
                hour_value=hour_value)
    trip.itineraries = list(its)
    with sessions() as s:
        s.add(trip)
        s.commit()


def _intervals(sessions):
    with sessions() as s:
        return [(it.fingerprint, iv) for it, iv in booking_intervals(s, WEIGHTS, [], {}, {})]


def test_a_booking_on_a_trip_with_an_hour_value_gives_no_interval(sessions):
    # Both trips have the same booking and the same other offer; only the trip with 30 EUR/h is left out.
    other = _it("other", 3, [("100", BOOKED_AT - timedelta(days=1))])
    _trip(sessions, _booked("with_value"), _it("other_value", 3, [("100", BOOKED_AT - timedelta(days=1))]),
          hour_value=D("30"))
    _trip(sessions, _booked("without_value"), other)
    assert _intervals(sessions) == [("without_value", (D("20.00"), None))]
