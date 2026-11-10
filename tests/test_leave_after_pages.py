"""The leave-after cost on each page of `row_cost()` (#2037, epic #2021): best offer, compare, share, calibration."""

import dataclasses
import re
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import require_login
from app.calibrate import booking_intervals
from app.main import app
from app.models import Fare, FarePrice, Itinerary, Leg, ScoreProfile, Trip
from app.profiles import to_config
from app.ranking import Weights
from app.web.pages import best_for_weights
from tests.test_ingest_best import setup  # noqa: F401 (fixture)

D = Decimal
ICE = [{"mode": "train", "carrier": "DB", "service_no": "ICE 5", "from_name": "Amsterdam Centraal",
        "to_name": "Köln Hbf", "depart_at": "2026-12-20T14:30:00+01:00", "arrive_at": "2026-12-20T17:00:00+01:00"}]
LATE = [dict(ICE[0], service_no="ICE 7", depart_at="2026-12-20T17:30:00+01:00",
             arrive_at="2026-12-20T20:00:00+01:00")]
FREE = {"hour_markup": D("0"), "transfer_markup": D("0")}


def _trip(setup, sessions, offers):  # noqa: F811
    setup([{"price_amount": "50.00", "price_currency": "EUR", "fare_name": "Sparpreis", "legs": legs}
           for legs in offers])
    with sessions() as s:
        trip = s.query(Trip).one()
        trip.leave_after = time(17, 0)
        s.commit()
        return trip.id


def _client():
    app.dependency_overrides[require_login] = lambda: None
    return TestClient(app)


def test_the_best_offer_costs_the_leave_part(setup, sessions):  # noqa: F811
    trip_id = _trip(setup, sessions, [ICE])
    with sessions() as s:
        trip = s.get(Trip, trip_id)
        totals = [best_for_weights(s, trip, Weights(**FREE, leave_hour_markup=D(v)))[2].total for v in ("0", "20")]
    assert totals[1] - totals[0] == D("50.00")


def test_the_compare_page_costs_the_leave_part(setup, sessions):  # noqa: F811
    trip_id = _trip(setup, sessions, [ICE, LATE])
    with sessions() as s:
        ids = [i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id))]
    client = _client()
    try:
        params = {"it": ids, "hour_markup": 0, "transfer_markup": 0}
        page = client.get(f"/trips/{trip_id}/compare", params={**params, "leave_hour_markup": 20}).text
        assert "€50 price + €50 leave 2 h 30 min before 17:00 = €100" in page
        page = client.get(f"/trips/{trip_id}/compare", params={**params, "leave_hour_markup": 0}).text
        assert "leave 2 h 30 min" not in page and "= €100" not in page
    finally:
        app.dependency_overrides.pop(require_login, None)


def _share_page(client, trip_id):
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)
    r = client.post(f"/trips/{trip_id}/share", data={"csrf_token": csrf})
    link = re.search(r'<pre class="share-link">([^<]+)</pre>', r.text).group(1)
    return client.get(link.removeprefix("http://testserver")).text


def test_the_share_page_costs_the_leave_part(setup, sessions):  # noqa: F811
    trip_id = _trip(setup, sessions, [ICE])
    client = _client()
    try:
        assert "leave 2 h 30 min" not in _share_page(client, trip_id)  # the default profile: €0
        with sessions() as s:
            p = ScoreProfile(name="Leave", is_default=False, config_json=to_config(Weights(**FREE, leave_hour_markup=D("20"))))
            s.add(p)
            s.flush()
            s.get(Trip, trip_id).profile_id = p.id
            s.commit()
        page = _share_page(client, trip_id)
        assert "leave 2 h 30 min before 17:00" in page and "100.00" in page
    finally:
        app.dependency_overrides.pop(require_login, None)


BOOKED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
DEPART = BOOKED_AT + timedelta(days=10)  # 13:00+01:00


def _it(name, hours, price, depart, **marks):
    arrive = depart + timedelta(hours=hours)
    leg = Leg(seq=0, mode="train", carrier="NS", service_no=name, from_name="A", to_name="B", depart_at=depart,
              depart_offset_min=60, arrive_at=arrive, arrive_offset_min=60)
    at = BOOKED_AT - timedelta(hours=1)
    fare = Fare(source="manual", latest_price=D(price), currency="EUR", latest_captured_at=at,
                prices=[FarePrice(price=D(price), currency="EUR", captured_at=at)])
    return Itinerary(fingerprint=name, depart_at=depart, arrive_at=arrive, duration_min=hours * 60, legs=[leg],
                     fares=[fare], **marks)


def test_the_calibration_counts_the_leave_part(sessions):
    booked = _it("booked", 2, "120", DEPART, booked=True, booked_at=BOOKED_AT)
    other = _it("other", 3, "100", DEPART + timedelta(hours=1))  # 14:00+01:00
    trip = Trip(title="T", origin_text="A", destination_text="B", status="planning", date_from=DEPART.date(),
                leave_after=time(14, 0))
    trip.itineraries = [booked, other]
    with sessions() as s:
        s.add(trip)
        s.commit()
    base = dataclasses.replace(Weights(), hour_markup=D("10"))
    with sessions() as s:
        found = [iv for w in (base, dataclasses.replace(base, leave_hour_markup=D("20")))
                 for _, iv in booking_intervals(s, w, [], {}, {})]
    assert found == [(D("20.00"), None), (D("40.00"), None)]  # 1 h before 14:00 costs the booking €20 more
