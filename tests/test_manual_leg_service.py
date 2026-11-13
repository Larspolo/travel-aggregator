"""The carrier and the number of each leg of the manual form (#2819)."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import make_password_hash
from app.main import app
from app.models import Leg, Trip

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
        t = Trip(title="Amsterdam", travelers=1)
        s.add(t)
        s.commit()
        return t.id


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _form(**kw):
    data = {"price_amount": "89.00", "price_currency": "EUR", "fare_name": "Saver", "utc_offset": "+01:00",
            "leg0_mode": "flight", "leg0_from_name": "Amsterdam", "leg0_to_name": "Berlin",
            "leg0_depart_at": "2026-12-01T08:00", "leg0_arrive_at": "2026-12-01T10:00",
            "leg0_carrier": "KLM", "leg0_service_no": "KL1923"}
    data.update(kw)
    return data


def _legs(engine):
    with Session(engine) as s:
        return s.scalars(select(Leg).order_by(Leg.seq)).all()


def test_carrier_and_number_are_stored(engine, client, trip_id):
    path = f"/trips/{trip_id}/offers/new"
    r = client.post(path, data=_form(csrf_token=_token(client, path)), follow_redirects=False)
    assert r.status_code == 303
    (leg,) = _legs(engine)
    assert (leg.carrier, leg.service_no) == ("KLM", "KL1923")


def test_empty_carrier_and_number_are_none(engine, client, trip_id):
    path = f"/trips/{trip_id}/offers/new"
    data = _form(csrf_token=_token(client, path), leg0_carrier="", leg0_service_no="")
    r = client.post(path, data=data, follow_redirects=False)
    assert r.status_code == 303
    (leg,) = _legs(engine)
    assert (leg.carrier, leg.service_no) == (None, None)


def test_carrier_only_leg_is_not_stored(engine, client, trip_id):
    path = f"/trips/{trip_id}/offers/new"
    data = _form(csrf_token=_token(client, path), leg0_mode="", leg0_from_name="", leg0_to_name="",
                 leg0_depart_at="", leg0_arrive_at="", leg0_carrier="KLM", leg0_service_no="KL1923")
    client.post(path, data=data, follow_redirects=False)
    assert _legs(engine) == []


def test_typed_carrier_and_number_are_shown_after_error(engine, client, trip_id):
    path = f"/trips/{trip_id}/offers/new"
    r = client.post(path, data=_form(csrf_token=_token(client, path), price_amount="-1"))
    assert r.status_code == 422
    assert 'value="KLM"' in r.text and 'value="KL1923"' in r.text
