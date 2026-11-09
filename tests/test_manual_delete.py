"""Delete a manual offer from the trip page (#1252)."""

import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import ingest
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Fare, FarePrice, Itinerary, Leg, Trip
from app.schemas import IngestIn

PASSWORD = "pw"
LEGS = [{"mode": "train", "from_name": "Utrecht", "to_name": "Berlin",
         "depart_at": "2026-12-01T08:00+01:00", "arrive_at": "2026-12-01T14:00+01:00"}]


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


def _store(engine, trip_id, source, price="49.90"):
    with Session(engine) as s:
        ingest.store(s, IngestIn(trip_id=trip_id, source=source, captured_at=datetime.now(timezone.utc),
                                 offers=[{"price_amount": price, "price_currency": "EUR", "legs": LEGS}]))
        s.commit()
        return s.scalars(select(Fare.id).where(Fare.source == source)).one()


def _count(engine, model):
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model))


def _path(trip_id, fare_id):
    return f"/trips/{trip_id}/fares/{fare_id}/delete"


def test_link_only_for_manual(engine, client, trip_id):
    manual = _store(engine, trip_id, "manual")
    bahn = _store(engine, trip_id, "bahn.de", "39.90")
    page = client.get(f"/trips/{trip_id}").text
    assert f'href="{_path(trip_id, manual)}"' in page
    assert _path(trip_id, bahn) not in page


def test_delete_only_manual_fare(engine, client, trip_id):
    manual = _store(engine, trip_id, "manual")
    page = client.get(_path(trip_id, manual))
    assert page.status_code == 200 and "Delete offer" in page.text and "Utrecht" in page.text
    assert "49.90" in page.text and "Cancel" in page.text
    r = client.post(_path(trip_id, manual), data={"csrf_token": _token(client, _path(trip_id, manual))},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{trip_id}"
    assert _count(engine, Fare) == 0 and _count(engine, FarePrice) == 0
    assert _count(engine, Itinerary) == 0 and _count(engine, Leg) == 0
    assert _count(engine, Capture) == 1


def test_delete_keeps_other_fare(engine, client, trip_id):
    manual = _store(engine, trip_id, "manual")
    bahn = _store(engine, trip_id, "bahn.de", "39.90")
    assert _count(engine, Itinerary) == 1
    r = client.post(_path(trip_id, manual), data={"csrf_token": _token(client, _path(trip_id, manual))},
                    follow_redirects=False)
    assert r.status_code == 303
    with Session(engine) as s:
        assert s.scalars(select(Fare.id)).all() == [bahn]
    assert _count(engine, Itinerary) == 1


def test_rejects_bahn_csrf_and_other_trip(engine, client, trip_id):
    manual = _store(engine, trip_id, "manual")
    bahn = _store(engine, trip_id, "bahn.de", "39.90")
    token = _token(client, _path(trip_id, manual))
    assert client.post(_path(trip_id, bahn), data={"csrf_token": token}).status_code == 400
    assert client.post(_path(trip_id, manual), data={}).status_code == 403
    assert client.post(_path(trip_id + 1, manual), data={"csrf_token": token}).status_code == 404
    assert client.get(_path(trip_id, 999)).status_code == 404
    assert _count(engine, Fare) == 2 and _count(engine, FarePrice) == 2
