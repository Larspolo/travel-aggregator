"""The manual offer form sets the travel class of the offer (#740)."""

import re

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
    data = {"price_amount": "49.90", "price_currency": "EUR", "fare_name": "Saver", "travel_class": "",
            "utc_offset": "+01:00",
            "leg0_mode": "train", "leg0_from_name": "Utrecht", "leg0_to_name": "Berlin",
            "leg0_depart_at": "2026-12-01T08:00", "leg0_arrive_at": "2026-12-01T14:00"}
    data.update(kw)
    return data


def _count(engine, model):
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model))


@pytest.mark.parametrize(("value", "stored"), [("first", "first"), ("standard", "standard"), ("", None)])
def test_class_is_stored(engine, client, trip_id, value, stored):
    path = f"/trips/{trip_id}/offers/new"
    r = client.post(path, data=_form(csrf_token=_token(client, path), travel_class=value), follow_redirects=False)
    assert r.status_code == 303
    with Session(engine) as s:
        fare = s.scalars(select(Fare)).one()
        assert fare.travel_class == stored


def test_unknown_class_stores_nothing(engine, client, trip_id):
    path = f"/trips/{trip_id}/offers/new"
    r = client.post(path, data=_form(csrf_token=_token(client, path), travel_class="business"))
    assert r.status_code == 422 and 'class="errors"' in r.text
    assert _count(engine, Itinerary) == 0 and _count(engine, Capture) == 0


def test_form_shows_the_class_select(engine, client, trip_id):
    html = client.get(f"/trips/{trip_id}/offers/new").text
    assert 'name="travel_class"' in html
    for label in ("Not set", "1st class", "2nd class"):
        assert f">{label}</option>" in html


def test_error_keeps_the_selected_class(engine, client, trip_id):
    path = f"/trips/{trip_id}/offers/new"
    r = client.post(path, data=_form(csrf_token=_token(client, path), travel_class="first", price_amount="-1"))
    assert r.status_code == 422
    assert re.search(r'value="first" selected>1st class<', r.text)
