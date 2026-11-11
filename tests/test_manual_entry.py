"""The manual offer form (#118)."""

import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Fare, Itinerary, Trip

PASSWORD = "pw"


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
            "leg0_mode": "train", "leg0_from_name": "Utrecht", "leg0_to_name": "Duisburg",
            "leg0_depart_at": "2026-12-01T08:00", "leg0_arrive_at": "2026-12-01T10:00",
            "leg1_mode": "train", "leg1_from_name": "Duisburg", "leg1_to_name": "Berlin",
            "leg1_depart_at": "2026-12-01T10:30", "leg1_arrive_at": "2026-12-01T14:30"}
    data.update(kw)
    return data


def _count(engine, model):
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model))


def test_valid_offer_is_stored(engine, client, trip_id):
    path = f"/trips/{trip_id}/offers/new"
    r = client.post(path, data=_form(csrf_token=_token(client, path)), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{trip_id}"
    with Session(engine) as s:
        it = s.scalars(select(Itinerary)).one()
        fare = s.scalars(select(Fare)).one()
        assert len(it.legs) == 2 and it.transfers == 1
        assert it.depart_at == datetime(2026, 12, 1, 7, 0, tzinfo=timezone.utc)
        assert (fare.source, str(fare.latest_price)) == ("manual", "49.90")


@pytest.mark.parametrize("bad", [{"leg0_arrive_at": "2026-12-01T07:00"}, {"price_amount": "-1"}])
def test_invalid_stores_nothing(engine, client, trip_id, bad):
    path = f"/trips/{trip_id}/offers/new"
    r = client.post(path, data=_form(csrf_token=_token(client, path), **bad))
    assert r.status_code == 422 and 'class="errors"' in r.text
    assert _count(engine, Itinerary) == 0 and _count(engine, Capture) == 0


def test_unknown_trip(engine, client, trip_id):
    assert client.get("/trips/999/offers/new").status_code == 404
    token = _token(client, f"/trips/{trip_id}/offers/new")
    assert client.post("/trips/999/offers/new", data=_form(csrf_token=token)).status_code == 404
    assert _count(engine, Itinerary) == 0


def test_login_and_csrf(engine, client, trip_id):
    path = f"/trips/{trip_id}/offers/new"
    anon = TestClient(app).post(path, data=_form(), follow_redirects=False)
    assert anon.status_code in (302, 303, 307) and "/login" in anon.headers["location"]
    assert client.post(path, data=_form(csrf_token="bad")).status_code == 403
    assert _count(engine, Itinerary) == 0
