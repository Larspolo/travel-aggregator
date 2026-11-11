"""The booking link field of the manual offer form (#2102)."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Fare, Itinerary, Trip

PASSWORD = "pw"
LINK = "https://www.bahn.de/buchung/x"


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


@pytest.fixture
def trip_id(engine):
    with Session(engine) as s:
        t = Trip(title="Berlin", travelers=1)
        s.add(t)
        s.commit()
        return t.id


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _form(**kw):
    data = {"price_amount": "49.90", "price_currency": "EUR", "fare_name": "Saver", "utc_offset": "+01:00",
            "leg0_mode": "train", "leg0_from_name": "Utrecht", "leg0_to_name": "Berlin",
            "leg0_depart_at": "2026-12-01T08:00", "leg0_arrive_at": "2026-12-01T14:00"}
    data.update(kw)
    return data


def _count(engine, model):
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model))


def test_the_form_has_a_booking_link_field(engine, client, trip_id):
    page = client.get(f"/trips/{trip_id}/offers/new").text
    assert 'type="url" name="booking_url"' in page
    assert ">Booking link<" in page


def test_a_booking_link_is_stored_and_shown_on_the_trip_page(engine, client, trip_id):
    path = f"/trips/{trip_id}/offers/new"
    r = client.post(path, data=_form(csrf_token=_token(client, path), booking_url=LINK), follow_redirects=False)
    assert r.status_code == 303
    with Session(engine) as s:
        fare = s.scalars(select(Fare)).one()
        assert fare.booking_url == LINK
    page = client.get(f"/trips/{trip_id}").text
    assert f'href="{LINK}"' in page


def test_an_empty_booking_link_stores_no_link(engine, client, trip_id):
    path = f"/trips/{trip_id}/offers/new"
    r = client.post(path, data=_form(csrf_token=_token(client, path), booking_url=""), follow_redirects=False)
    assert r.status_code == 303
    with Session(engine) as s:
        fare = s.scalars(select(Fare)).one()
        assert fare.booking_url is None


def test_a_javascript_link_is_rejected_and_stores_nothing(engine, client, trip_id):
    path = f"/trips/{trip_id}/offers/new"
    r = client.post(path, data=_form(csrf_token=_token(client, path), booking_url="javascript:alert(1)"))
    assert r.status_code == 422
    assert "booking_url" in r.text
    assert _count(engine, Itinerary) == 0 and _count(engine, Capture) == 0
