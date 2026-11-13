"""The manual form opens with the reservation when no itinerary matches the uploaded mail (#2298)."""

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash, token_limiter
from app.main import app
from app.models import Itinerary, Leg, Trip

PASSWORD = "pw"
FIX = Path(__file__).parent / "fixtures" / "booking_mail"
FLIGHT = (FIX / "flight.eml").read_bytes()
TRAIN = (FIX / "train.eml").read_bytes()
NO_MATCH = "No itinerary of this trip matches the reservation"


def utc(h, m):
    return datetime(2027, 4, 2, h, m, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _limiter():
    token_limiter.reset()
    yield
    token_limiter.reset()


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def add_train_trip(sessions):
    """A trip with one train itinerary and no flight."""
    with sessions() as s:
        trip = Trip(title="T", origin_text="Amsterdam", destination_text="Barcelona", status="planning", travelers=2)
        it = Itinerary(fingerprint="f-train", depart_at=utc(9, 0), arrive_at=utc(15, 35), duration_min=395,
                       legs=[Leg(seq=0, mode="train", carrier="Example Rail", service_no="ICE123",
                                 from_name="Amsterdam Centraal", to_name="Köln Hbf", depart_at=utc(9, 0),
                                 depart_offset_min=60, arrive_at=utc(11, 40), arrive_offset_min=60)])
        trip.itineraries = [it]
        s.add(trip)
        s.commit()
        return trip.id


def upload(client, trip_id, name, raw):
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)
    return client.post(f"/trips/{trip_id}/booking-mail", data={"csrf_token": token},
                       files={"file": (name, raw, "message/rfc822")})


def field(html, name):
    """The value of the input or select of the form with this name."""
    match = re.search(rf'name="{name}"[^>]*value="([^"]*)"', html)
    assert match, f"no input {name}"
    return match.group(1)


def test_flight_opens_form_with_reservation(client, sessions):
    trip_id = add_train_trip(sessions)
    r = upload(client, trip_id, "mail.eml", FLIGHT)
    assert r.status_code == 200
    html = r.text
    assert NO_MATCH in html
    assert 'action="/trips/%d/offers/new"' % trip_id in html
    assert re.search(r'<option value="flight" selected>', html)
    assert field(html, "leg0_from_name") == "AMS"
    assert field(html, "leg0_to_name") == "Barcelona El Prat"
    assert field(html, "leg0_depart_at") == "2027-04-02T07:30"
    assert field(html, "leg0_arrive_at") == "2027-04-02T07:45"
    assert field(html, "leg0_carrier") == "Example Air"
    assert field(html, "leg0_service_no") == "110"
    assert field(html, "price_amount") == "120"
    assert field(html, "price_currency") == "EUR"
    assert field(html, "utc_offset") == "+00:00"
    assert field(html, "travelers") == "2"


def test_no_match_saves_nothing(client, sessions):
    trip_id = add_train_trip(sessions)
    upload(client, trip_id, "mail.eml", FLIGHT)
    with sessions() as s:
        trip = s.get(Trip, trip_id)
        assert [it.booked for it in trip.itineraries] == [False]
        assert all(it.booked_price is None for it in trip.itineraries)
