"""Mark the matching itinerary as booked from an uploaded confirmation e-mail (#2297)."""

import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth import make_password_hash, token_limiter
from app.main import app
from app.models import Capture, Fare, Itinerary, Leg, Setting, Trip
from app.schemas import MAX_MAIL_BYTES

PASSWORD = "pw"
FIX = Path(__file__).parent / "fixtures" / "booking_mail"
TRAIN = (FIX / "train.eml").read_bytes()


def utc(h, m):
    return datetime(2027, 3, 1, h, m, tzinfo=timezone.utc)


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


def add(sessions, first_depart=utc(9, 0)):
    """A trip with the 2 train legs of the fixture (10:00-12:40 and 13:15-16:35 at +01:00)."""
    with sessions() as s:
        trip = Trip(title="T", origin_text="Amsterdam", destination_text="Paris", status="planning")
        it = Itinerary(fingerprint="f-mail", depart_at=first_depart, arrive_at=utc(15, 35), duration_min=395,
                       legs=[Leg(seq=0, mode="train", carrier="Example Rail", service_no="ICE123",
                                 from_name="Amsterdam Centraal", to_name="Köln Hbf", depart_at=first_depart,
                                 depart_offset_min=60, arrive_at=utc(11, 40), arrive_offset_min=60),
                             Leg(seq=1, mode="train", carrier="Example Rail", service_no="9425",
                                 from_name="Köln Hbf", to_name="Paris Nord", depart_at=utc(12, 15),
                                 depart_offset_min=60, arrive_at=utc(15, 35), arrive_offset_min=60)])
        trip.itineraries = [it]
        Fare(itinerary=it, source="ns", latest_price=Decimal("95"), currency="EUR", latest_captured_at=utc(8, 0))
        s.add(trip)
        s.commit()
        return trip.id, it.id


def upload(client, trip_id, raw):
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)
    return client.post(f"/trips/{trip_id}/booking-mail", data={"csrf_token": token},
                       files={"file": ("mail.eml", raw, "message/rfc822")})


def state(sessions, it_id):
    with sessions() as s:
        it = s.get(Itinerary, it_id)
        return it.booked, it.booked_price, it.booked_currency, it.booking_code


def counts(sessions):
    with sessions() as s:
        return s.scalar(select(func.count()).select_from(Capture)), s.scalar(select(func.count()).select_from(Setting))


def test_upload_marks_booked_and_upcoming_shows_it(client, sessions):
    trip_id, it_id = add(sessions)
    before = counts(sessions)
    r = upload(client, trip_id, TRAIN)
    assert "as booked: paid 89.90 EUR, code XYZ123" in r.text
    assert state(sessions, it_id) == (True, Decimal("89.90"), "EUR", "XYZ123")
    assert counts(sessions) == before  # P5: nothing of the mail is stored
    page = client.get("/upcoming").text
    assert "XYZ123" in page and "89.90" in page


def test_second_upload_changes_nothing(client, sessions):
    trip_id, it_id = add(sessions)
    upload(client, trip_id, TRAIN)
    r = upload(client, trip_id, TRAIN)
    assert "already booked" in r.text
    assert state(sessions, it_id) == (True, Decimal("89.90"), "EUR", "XYZ123")


@pytest.mark.parametrize("raw, text", [
    ((FIX / "no_markup.eml").read_bytes(), "No reservation found in this e-mail"),
    (b"x" * (MAX_MAIL_BYTES + 1), "The e-mail is too large"),
])
def test_bad_mail_gives_message(client, sessions, raw, text):
    trip_id, it_id = add(sessions)
    assert text in upload(client, trip_id, raw).text
    assert state(sessions, it_id) == (False, None, None, None)


def test_other_times_do_not_match(client, sessions):
    trip_id, it_id = add(sessions, first_depart=utc(9, 30))
    assert "No itinerary of this trip matches the reservation" in upload(client, trip_id, TRAIN).text
    assert state(sessions, it_id) == (False, None, None, None)


def test_page_has_upload_field(client, sessions):
    trip_id, _ = add(sessions)
    assert "Booked? Upload the confirmation e-mail (.eml)" in client.get(f"/trips/{trip_id}").text
