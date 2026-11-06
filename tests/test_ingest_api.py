"""POST /api/ingest (#6): a valid body stores the itinerary, legs, fare and price row; bad input gets 401, 404 or 422."""

import copy
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import tokens
from app.main import app
from app.models import Fare, FarePrice, Itinerary, Leg, Trip

BODY = {
    "trip_id": 0, "source": "bahn.de", "parser_version": "1.0.0", "captured_at": "2026-11-03T19:41:00Z",
    "page_url": "https://www.bahn.de/buchung/fahrplan/suche",
    "search_context": {"from": "Amsterdam", "to": "Zürich", "date": "2026-12-20", "travelers": 1},
    "offers": [{
        "price_amount": 89.90, "price_currency": "EUR", "fare_name": "Sparpreis", "flexibility": "non_refundable",
        "booking_url": "https://www.bahn.de/buchung/x",
        "legs": [
            {"mode": "train", "carrier": "DB", "service_no": "ICE 105", "from_name": "Amsterdam Centraal",
             "to_name": "Basel SBB", "depart_at": "2026-12-20T07:34:00+01:00", "arrive_at": "2026-12-20T14:02:00+01:00"},
            {"mode": "train", "carrier": "SBB", "service_no": "IC 61", "from_name": "Basel SBB",
             "to_name": "Zürich HB", "depart_at": "2026-12-20T14:33:00+01:00", "arrive_at": "2026-12-20T15:26:00+01:00"},
        ],
    }],
}


@pytest.fixture
def setup(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Amsterdam – Zürich")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    return TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id


def body(trip_id, **change):
    b = copy.deepcopy(BODY)
    b["trip_id"] = trip_id
    b.update(change)
    return b


def test_a_valid_post_stores_itinerary_legs_fare_and_price(setup, sessions):
    client, auth, trip_id = setup
    r = client.post("/api/ingest", json=body(trip_id), headers=auth)
    assert r.status_code == 200 and r.json() == {"created": 1, "updated": 0, "unchanged": 0}
    with sessions() as s:
        it = s.scalar(select(Itinerary))
        assert (it.trip_id, it.transfers, it.duration_min, it.mode_summary) == (trip_id, 1, 472, "train")
        assert it.depart_at == datetime(2026, 12, 20, 6, 34, tzinfo=UTC)
        legs = s.scalars(select(Leg).order_by(Leg.seq)).all()
        assert [leg.service_no for leg in legs] == ["ICE 105", "IC 61"] and legs[0].depart_offset_min == 60
        fare = s.scalar(select(Fare))
        assert (fare.source, fare.fare_name, fare.latest_price, fare.currency) == ("bahn.de", "Sparpreis",
                                                                                    Decimal("89.90"), "EUR")
        assert s.scalar(select(func.count()).select_from(FarePrice)) == 1


def test_the_same_journey_again_adds_a_price_row_not_an_itinerary(setup, sessions):
    client, auth, trip_id = setup
    client.post("/api/ingest", json=body(trip_id), headers=auth)
    later = body(trip_id, captured_at="2026-11-04T08:00:00Z")
    later["offers"][0]["price_amount"] = "79.90"
    assert client.post("/api/ingest", json=later, headers=auth).json() == {"created": 0, "updated": 1, "unchanged": 0}
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Itinerary)) == 1
        assert s.scalar(select(func.count()).select_from(FarePrice)) == 2
        assert s.scalar(select(Fare)).latest_price == Decimal("79.90")


@pytest.mark.parametrize("auth", [{}, {"Authorization": "Bearer wrong"}])
def test_a_bad_token_gets_401(setup, sessions, auth):
    client, _, trip_id = setup
    assert client.post("/api/ingest", json=body(trip_id), headers=auth).status_code == 401
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Itinerary)) == 0


def test_an_unknown_trip_gets_404(setup):
    client, auth, trip_id = setup
    assert client.post("/api/ingest", json=body(trip_id + 1), headers=auth).status_code == 404


def _bad(trip_id, path, value):
    b = body(trip_id)
    target = b
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return b


@pytest.mark.parametrize("path, value", [
    (("offers", 0, "legs", 0, "depart_at"), "2026-12-20T07:34:00"),       # a naive time
    (("captured_at",), "2026-11-03T19:41:00"),                               # a naive time
    (("offers", 0, "price_amount"), "89.999"),                               # more than 2 decimals
    (("offers", 0, "price_amount"), "a lot"),
    (("offers", 0, "price_currency"), "euro"),
    (("offers", 0, "legs"), []),
    (("offers", 0, "legs", 0, "mode"), "rocket"),
    (("offers", 0, "booking_url"), "javascript:alert(1)"),
    (("offers", 0, "legs", 1, "depart_at"), "2026-12-20T13:00:00+01:00"),  # departs before the leg before arrives
    (("offers",), []),                                                       # no raw and no offers
])
def test_bad_input_gets_422(setup, sessions, path, value):
    client, auth, trip_id = setup
    assert client.post("/api/ingest", json=_bad(trip_id, path, value), headers=auth).status_code == 422
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Itinerary)) == 0


def test_too_many_offers_get_422_and_a_too_large_body_413(setup):
    client, auth, trip_id = setup
    many = body(trip_id)
    many["offers"] = many["offers"] * 501
    assert client.post("/api/ingest", json=many, headers=auth).status_code == 422
    r = client.post("/api/ingest", content=b" " * 5_000_001, headers={**auth, "Content-Type": "application/json"})
    assert r.status_code == 413


def test_raw_only_is_accepted_and_stores_nothing_yet(setup):
    client, auth, trip_id = setup
    r = client.post("/api/ingest", json=body(trip_id, offers=[], raw={"journeys": []}), headers=auth)
    assert r.status_code == 200 and r.json() == {"created": 0, "updated": 0, "unchanged": 0}
