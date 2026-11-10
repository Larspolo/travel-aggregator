"""The interval of each booking from the offers of its trip at `booked_at` (#1710, epic #1708)."""

import dataclasses
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.calibrate import best_fit, booking_intervals
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


def _trip(sessions, *its):
    trip = Trip(title="T", origin_text="A", destination_text="B", status="planning", date_from=DEPART.date())
    trip.itineraries = list(its)
    with sessions() as s:
        s.add(trip)
        s.commit()


def _intervals(sessions):
    with sessions() as s:
        return [(it.fingerprint, iv) for it, iv in booking_intervals(s, WEIGHTS, [], {}, {})]


def test_a_fare_counts_at_its_price_at_booked_at(sessions):
    # The other offer: 100 EUR and 3 h at booked_at, 60 EUR later. At 100 EUR the booking needs 20 EUR/h.
    other = _it("other", 3, [("100", BOOKED_AT - timedelta(days=1)), ("60", BOOKED_AT + timedelta(days=1))])
    _trip(sessions, _booked(), other)
    assert _intervals(sessions) == [("booked", (D("20.00"), None))]


def test_departed_and_later_offers_do_not_limit_the_interval(sessions):
    other = _it("other", 3, [("100", BOOKED_AT - timedelta(days=1))])
    departed = _it("departed", 1, [("10", BOOKED_AT - timedelta(days=3))], depart=BOOKED_AT - timedelta(hours=2))
    later = _it("later", 1, [("10", BOOKED_AT + timedelta(minutes=5))])
    _trip(sessions, _booked(), other, departed, later)
    assert _intervals(sessions) == [("booked", (D("20.00"), None))]


def test_a_cancelled_booking_counts_and_an_open_journey_does_not(sessions):
    other = _it("other", 3, [("100", BOOKED_AT - timedelta(days=1))])
    cancelled = _booked("cancelled", hours=4, price="60", booked=False, cancelled_at=BOOKED_AT + timedelta(days=2))
    open_one = _booked("open", hours=1, price="200", booked=False)
    _trip(sessions, _booked(), other, cancelled, open_one)
    found = dict(_intervals(sessions))
    assert set(found) == {"booked", "cancelled"}
    # The cancelled journey: 1 hour more than "other" for 40 EUR less; "booked" limits it from above too.
    assert found["cancelled"] == (None, D("30.00"))


def test_a_booking_with_no_other_offer_has_no_interval(sessions):
    _trip(sessions, _booked())
    assert _intervals(sessions) == [("booked", None)]


def test_the_two_bookings_of_the_epic_fit_20_to_40(sessions):
    _trip(sessions, _booked(), _it("other", 3, [("100", BOOKED_AT - timedelta(days=1))]))
    _trip(sessions, _booked("slow", hours=4, price="60"), _it("fast", 3, [("100", BOOKED_AT - timedelta(days=1))]))
    assert best_fit(iv for _, iv in _intervals(sessions)) == (D("20.00"), D("40.00"), 2, 2)


def test_the_stored_fares_do_not_change(sessions):
    _trip(sessions, _booked(), _it("other", 3, [("100", BOOKED_AT - timedelta(days=1)),
                                                 ("60", BOOKED_AT + timedelta(days=1))]))
    with sessions() as s:
        booking_intervals(s, WEIGHTS, [], {}, {})
        assert not s.dirty
        assert {f.latest_price for f in s.scalars(select(Fare))} == {D("120"), D("60")}
