"""The manual offer form says for how many travelers its price is (#1028)."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip

PASSWORD = "pw"


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


@pytest.fixture
def trip_id(engine):
    with Session(engine) as s:
        t = Trip(title="Berlin", travelers=2)
        s.add(t)
        s.commit()
        return t.id


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _post(client, trip_id, **kw):
    data = {"price_amount": "180", "price_currency": "EUR", "fare_name": "", "travel_class": "",
            "utc_offset": "+01:00", "travelers": "1",
            "leg0_mode": "train", "leg0_from_name": "Utrecht", "leg0_to_name": "Berlin",
            "leg0_depart_at": "2026-12-01T08:00", "leg0_arrive_at": "2026-12-01T14:00"}
    data.update(kw, csrf_token=_token(client, f"/trips/{trip_id}/offers/new"))
    return client.post(f"/trips/{trip_id}/offers/new", data=data, follow_redirects=False)


def _breakdown(client, trip_id):
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "0", "transfer_markup": "0"}).text
    return [c.strip() for c in re.findall(r'<[a-z]+ class="breakdown">([^<]*)', page)]


def test_the_field_has_the_travelers_of_the_trip_as_default(client, trip_id):
    page = client.get(f"/trips/{trip_id}/offers/new").text
    assert re.search(r'name="travelers" type="number" min="1" max="9" step="1" value="2"', page)
    assert "Price for N travelers" in page


def test_a_price_for_1_traveler_ranks_as_before(client, trip_id, engine):
    assert _post(client, trip_id).status_code == 303
    with Session(engine) as s:
        assert s.scalar(select(Capture.travelers)) == 1
    assert _breakdown(client, trip_id) == ["€180 price = €180"]


def test_a_group_price_ranks_per_traveler(client, trip_id, engine):
    assert _post(client, trip_id, travelers="2").status_code == 303
    with Session(engine) as s:
        assert s.scalar(select(Capture.travelers)) == 2
    (text,) = _breakdown(client, trip_id)
    assert "€180 for 2 travelers" in text and text.endswith("= €90"), text


@pytest.mark.parametrize("bad", ["0", "10", "two"])
def test_a_bad_count_shows_an_error_and_stores_nothing(client, trip_id, engine, bad):
    r = _post(client, trip_id, travelers=bad)
    assert r.status_code == 422 and "1 to 9 travelers" in r.text
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Capture)) == 0
