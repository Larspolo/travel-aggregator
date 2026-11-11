"""Each trip uses its own access and egress places in the days strip, in a booking and in the hour fit (#2107, #2109)."""

import dataclasses
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.calibrate import booking_intervals
from app.models import AccessTime, Itinerary, Leg, Trip, TripAccessTime
from app.ranking import Weights
from tests.test_trip_days_strip import _set_range, _strip
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

D = Decimal


def _global_egress(sessions):
    with sessions() as s:
        s.add(AccessTime(place_text="Zürich HB", kind="egress", minutes=40, cost=D("0")))
        s.commit()


def _override(sessions, trip_id, minutes):
    with sessions() as s:
        s.add(TripAccessTime(trip_id=trip_id, place_text="Zürich HB", kind="egress", minutes=minutes, cost=D("0")))
        s.commit()


def _booked_url(trip_id, itinerary_id):
    return f"/trips/{trip_id}/itineraries/{itinerary_id}/booked"


def _csrf(client, trip_id):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)


def _itinerary_id(sessions, trip_id, service_no):
    with sessions() as s:
        for it in s.query(Itinerary).filter_by(trip_id=trip_id):
            if it.legs and it.legs[0].service_no == service_no:
                return it.id
    raise AssertionError(f"no itinerary {service_no}")


def test_the_days_strip_shows_the_total_with_the_trip_override(trip, sessions):  # noqa: F811
    client, auth, a_id = trip
    _global_egress(sessions)
    _override(sessions, a_id, 10)  # 10 min at the default €15/h = €2.50
    with sessions() as s:
        c = Trip(title="C", origin_text="Amsterdam", destination_text="Zürich")
        s.add(c)
        s.commit()
        c_id = c.id
    for t in (a_id, c_id):
        _set_range(sessions, t, date(2026, 12, 20), date(2026, 12, 21))
        ingest(client, auth, t, [direct("150.00")])
    # 150 + 60 min of travel + egress: 212.50 with the override, 220 with the global 40 min (€10)
    strip_a = _strip(client.get(f"/trips/{a_id}").text)
    strip_c = _strip(client.get(f"/trips/{c_id}").text)
    assert "212.50" in strip_a and "212.50" not in strip_c
    assert "220" in strip_c or "220.00" in strip_c


def test_a_booking_keeps_the_paid_fare_and_the_override_total(trip, sessions):  # noqa: F811
    client, auth, a_id = trip
    _global_egress(sessions)
    _override(sessions, a_id, 10)
    ingest(client, auth, a_id, [direct("150.00")])
    it_id = _itinerary_id(sessions, a_id, "ICE 9")
    client.post(_booked_url(a_id, it_id), data={"csrf_token": _csrf(client, a_id)}, follow_redirects=False)
    with sessions() as s:
        it = s.get(Itinerary, it_id)
        assert it.booked and it.booked_price == D("150.00")  # the paid fare is the fare, not the total
    assert "212.50" in client.get(f"/trips/{a_id}").text


def _leg(name, depart, hours, to_name="Zürich HB"):
    arrive = depart + timedelta(hours=hours)
    return Leg(seq=0, mode="train", carrier="NS", service_no=name, from_name="A", to_name=to_name,
               depart_at=depart, depart_offset_min=60, arrive_at=arrive, arrive_offset_min=60)


def _interval_for(sessions, overrides_minutes):
    """The interval of a booking (120 EUR, 2 h) against an offer (100 EUR, 3 h) in a trip with the given override
    (None: only the global 40 min egress)."""
    booked_at = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    depart = booked_at + timedelta(days=10)
    from app.models import Fare, FarePrice
    booking = Itinerary(fingerprint="b", depart_at=depart, arrive_at=depart + timedelta(hours=2), duration_min=120,
                        legs=[_leg("B", depart, 2)], booked=True, booked_at=booked_at,
                        fares=[Fare(source="manual", latest_price=D("120"), currency="EUR",
                                    latest_captured_at=booked_at - timedelta(hours=1),
                                    prices=[FarePrice(price=D("120"), currency="EUR",
                                                      captured_at=booked_at - timedelta(hours=1))])])
    other = Itinerary(fingerprint="o", depart_at=depart, arrive_at=depart + timedelta(hours=3), duration_min=180,
                      legs=[_leg("O", depart, 3, to_name="Basel SBB")],  # no egress: it ends at another station
                      fares=[Fare(source="manual", latest_price=D("100"), currency="EUR",
                                  latest_captured_at=booked_at - timedelta(hours=1),
                                  prices=[FarePrice(price=D("100"), currency="EUR",
                                                    captured_at=booked_at - timedelta(hours=1))])])
    with sessions() as s:
        t = Trip(title="T", origin_text="A", destination_text="Zürich HB", status="planning", date_from=depart.date())
        t.itineraries = [booking, other]
        s.add(t)
        s.flush()
        if overrides_minutes is not None:
            s.add(TripAccessTime(trip_id=t.id, place_text="Zürich HB", kind="egress", minutes=overrides_minutes,
                                 cost=D("0")))
        s.commit()
        trip_id = t.id
    with sessions() as s:
        weights = dataclasses.replace(Weights(), hour_markup=D("10"))
        for it, iv in booking_intervals(s, weights, [], {}, {}):
            if it.trip_id == trip_id:
                return iv
    raise AssertionError("no booking interval")


def test_the_hour_fit_uses_the_trip_override(sessions):
    _global_egress(sessions)
    with_override = _interval_for(sessions, 0)
    with_global = _interval_for(sessions, None)
    assert with_override is not None and with_global is not None
    assert with_override != with_global
