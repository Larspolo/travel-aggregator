"""The ingest response tells the best offer of the trip and if the capture made it better (#880)."""

import copy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.main import app
from app.models import Itinerary, Trip

LEGS = [
    {"mode": "train", "carrier": "DB", "service_no": "ICE 105", "from_name": "Amsterdam Centraal",
     "to_name": "Basel SBB", "depart_at": "2026-12-20T07:34:00+01:00", "arrive_at": "2026-12-20T14:02:00+01:00"},
    {"mode": "train", "carrier": "SBB", "service_no": "IC 61", "from_name": "Basel SBB",
     "to_name": "Zürich HB", "depart_at": "2026-12-20T14:33:00+01:00", "arrive_at": "2026-12-20T15:26:00+01:00"},
]


def offer(price, legs=LEGS):
    return {"price_amount": price, "price_currency": "EUR", "fare_name": "Sparpreis", "legs": copy.deepcopy(legs)}


def other_legs(hour):
    return [{"mode": "train", "carrier": "DB", "service_no": f"ICE {hour}", "from_name": "Amsterdam Centraal",
             "to_name": "Zürich HB", "depart_at": f"2026-12-20T{hour:02d}:00:00+01:00",
             "arrive_at": f"2026-12-20T{hour + 7:02d}:00:00+01:00"}]


@pytest.fixture
def setup(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Amsterdam – Zürich")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {token}"}

    def post(offers):
        b = {"trip_id": trip_id, "source": "bahn.de", "parser_version": "1.0.0",
             "captured_at": "2026-11-03T19:41:00Z", "page_url": "https://www.bahn.de/x", "offers": offers}
        r = client.post("/api/ingest", json=b, headers=auth)
        assert r.status_code == 200, r.text
        return r.json()
    return post


def test_first_cheaper_and_more_expensive_captures(setup):
    first = setup([offer("120.00")])["best"]
    assert first["price"] == "120.00" and first["currency"] == "EUR" and first["new"] is True
    assert isinstance(first["total"], str)
    assert first["summary"] == "ICE 105 07:34 → IC 61 15:26"
    cheaper = setup([offer("80.00", other_legs(9))])["best"]
    assert cheaper["price"] == "80.00" and cheaper["new"] is True
    assert cheaper["summary"] == "ICE 9 09:00 → 16:00"
    worse = setup([offer("300.00", other_legs(11))])["best"]
    assert worse["price"] == "80.00" and worse["total"] == cheaper["total"] and worse["new"] is False


def test_a_hidden_itinerary_is_never_best(setup, sessions):
    setup([offer("50.00")])
    with sessions() as s:
        s.scalar(select(Itinerary)).hidden = True
        s.commit()
    best = setup([offer("90.00", other_legs(10))])["best"]
    assert best["price"] == "90.00"


def test_an_empty_trip_with_rejected_offers_gives_null(setup):
    bad = offer("10.00")
    bad["legs"] = []
    assert setup([bad])["best"] is None


def test_summary_uses_the_original_offset(setup):
    legs = [{"mode": "train", "carrier": "NS", "service_no": "IC 1", "from_name": "A", "to_name": "B",
             "depart_at": "2026-12-20T07:12:00Z", "arrive_at": "2026-12-20T08:00:00Z"}]
    legs[0]["depart_at"] = "2026-12-20T08:12:00+01:00"
    legs[0]["arrive_at"] = "2026-12-20T09:00:00+01:00"
    assert setup([offer("20.00", legs)])["best"]["summary"] == "IC 1 08:12 → 09:00"
