"""The capture delete through the whole flow (#2188, #2186, #2187): two bahn.de captures go through the ingest API, the
newer one is deleted on its page, and the trip page, the captures page and the source health show the first one only."""

import copy
import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Fare, Trip
from app.sourcehealth import source_health
from tests.test_ingest_api import BODY

PASSWORD = "pw"


def _csrf(c, path):
    return re.search(r'csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _leg(service_no, carrier, from_name, to_name, depart, arrive):
    return {"mode": "train", "carrier": carrier, "service_no": service_no, "from_name": from_name,
            "to_name": to_name, "depart_at": depart, "arrive_at": arrive}


ICE_105 = _leg("ICE 105", "DB", "Amsterdam Centraal", "Basel SBB", "2026-12-20T07:34:00+01:00",
               "2026-12-20T14:02:00+01:00")
IC_61 = _leg("IC 61", "SBB", "Basel SBB", "Zürich HB", "2026-12-20T14:33:00+01:00", "2026-12-20T15:26:00+01:00")
IC_2021 = _leg("IC 2021", "SBB", "Amsterdam Centraal", "Zürich HB", "2026-12-20T09:00:00+01:00",
               "2026-12-20T15:30:00+01:00")


def _offer(price, legs, fare_name="Sparpreis"):
    return {"price_amount": price, "price_currency": "EUR", "fare_name": fare_name, "flexibility": "non_refundable",
            "booking_url": "https://www.bahn.de/buchung/x", "legs": legs}


def _body(trip_id, captured_at, offers):
    b = copy.deepcopy(BODY)
    b.update(trip_id=trip_id, captured_at=captured_at, offers=offers)
    return b


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Amsterdam – Zürich")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c, "/login")})
    return c, {"Authorization": f"Bearer {token}"}, trip_id


def test_deleting_the_newer_capture_leaves_the_first_one_everywhere(client, sessions):
    c, auth, trip_id = client

    # A: ICE 105 + IC 61 at 89.90; B (newer): the same ICE 105 at 79.00 and a different IC 2021 at 45.00
    a_body = _body(trip_id, "2026-11-03T19:41:00Z", [_offer(89.90, [ICE_105, IC_61])])
    b_body = _body(trip_id, "2026-11-04T19:41:00Z",
                   [_offer(79.00, [ICE_105, IC_61]), _offer(45.00, [IC_2021], fare_name="Sparpreis")])
    assert c.post("/api/ingest", json=a_body, headers=auth).status_code == 200
    assert c.post("/api/ingest", json=b_body, headers=auth).status_code == 200
    with sessions() as s:
        a_id, b_id = [cap.id for cap in s.scalars(select(Capture).order_by(Capture.id))]
        ice_fare = s.scalars(select(Fare).where(Fare.fare_name == "Sparpreis")).all()
        assert len(ice_fare) == 2  # ICE 105 and IC 2021 are two fares

    # the owner deletes B on its confirm page
    confirm = c.get(f"/captures/{b_id}/delete")
    assert confirm.status_code == 200 and "This cannot be undone." in confirm.text
    r = c.post(f"/captures/{b_id}/delete", data={"csrf_token": _csrf(c, f"/captures/{b_id}/delete")},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{trip_id}/captures"

    # the trip page: ICE 105 at the price of A, no IC 2021
    trip_page = c.get(f"/trips/{trip_id}").text
    assert "ICE 105" in trip_page
    assert "IC 2021" not in trip_page
    with sessions() as s:
        fares = s.scalars(select(Fare)).all()
        assert len(fares) == 1  # IC 2021 went with B
        assert fares[0].latest_price == Decimal("89.90")
        assert len(fares[0].prices) == 1  # the price history of ICE 105 has 1 point

    # the captures page lists A only
    captures = c.get(f"/trips/{trip_id}/captures").text
    assert f"/captures/{a_id}/delete" in captures
    assert f"/captures/{b_id}/delete" not in captures
    assert c.get(f"/captures/{b_id}/delete").status_code == 404

    # the source health counts one capture of bahn.de: the newest good capture is A
    with sessions() as s:
        assert s.query(Capture).filter_by(source="bahn.de").count() == 1
        entry = next(e for e in source_health(s) if e["source"] == "bahn.de")
        assert entry["last_at"].replace(tzinfo=UTC) == datetime(2026, 11, 3, 19, 41, tzinfo=UTC)
