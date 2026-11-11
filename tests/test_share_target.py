"""The share path (#2104): a shared page opens the manual offer form with a trip dropdown."""

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




def test_a_shared_url_and_title_fill_the_form_and_save_to_the_chosen_trip(engine, client, trip_id):
    page = client.get("/share?url=https://www.bahn.de/buchung/x&title=ICE%20105").text
    assert f'value="{LINK}"' in page
    assert 'value="ICE 105"' in page
    assert f'<option value="{trip_id}"' in page and 'action="/share"' in page
    data = _form(csrf_token=_token(client, "/share"), booking_url=LINK, fare_name="ICE 105", trip_id=str(trip_id))
    r = client.post("/share", data=data, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{trip_id}"
    with Session(engine) as s:
        fare = s.scalars(select(Fare)).one()
        assert fare.booking_url == LINK and fare.itinerary.trip_id == trip_id


def test_the_address_in_the_text_is_the_link(engine, client, trip_id):
    page = client.get("/share", params={"text": "See this https://www.flixbus.com/x"}).text
    assert 'value="https://www.flixbus.com/x"' in page


def test_a_javascript_address_gives_the_error_and_no_link_and_a_long_title_is_cut(engine, client, trip_id):
    page = client.get("/share", params={"url": "javascript:alert(1)", "title": "A" * 150}).text
    assert "The shared address is not a web address" in page
    assert "javascript:" not in page
    assert f'value="{"A" * 100}"' in page and "A" * 101 not in page


def test_an_archived_trip_is_not_in_the_dropdown_and_cannot_be_chosen(engine, client):
    with Session(engine) as s:
        t = Trip(title="Old", status="archived")
        s.add(t)
        s.commit()
        old = t.id
    assert f'<option value="{old}"' not in client.get("/share").text
    r = client.post("/share", data=_form(csrf_token=_token(client, "/share"), trip_id=str(old)))
    assert r.status_code == 422 and _count(engine, Capture) == 0 and _count(engine, Itinerary) == 0
