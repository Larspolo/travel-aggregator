"""Change the price of a manual offer (#1253)."""

import re
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ingest
from app.auth import make_password_hash
from app.main import app
from app.models import Fare, FarePrice, Trip
from app.schemas import IngestIn

PASSWORD = "pw"
LEGS = [{"mode": "train", "from_name": "Utrecht", "to_name": "Berlin",
         "depart_at": "2026-12-01T08:00+01:00", "arrive_at": "2026-12-01T14:00+01:00"}]
LEGS2 = [{"mode": "train", "from_name": "Utrecht", "to_name": "Berlin",
          "depart_at": "2026-12-01T09:00+01:00", "arrive_at": "2026-12-01T15:00+01:00"}]


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


@pytest.fixture
def client(monkeypatch, sessions):
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


def _store(engine, trip_id, source, price, legs=LEGS):
    with Session(engine) as s:
        ingest.store(s, IngestIn(trip_id=trip_id, source=source, captured_at=datetime.now(timezone.utc),
                                 offers=[{"price_amount": price, "price_currency": "EUR", "legs": legs}]))
        s.commit()
        return s.scalars(select(Fare.id).where(Fare.source == source)).one()


def _prices(engine, fare_id):
    with Session(engine) as s:
        return [p.price for p in s.scalars(select(FarePrice).where(FarePrice.fare_id == fare_id)
                                           .order_by(FarePrice.captured_at))]


def _post(client, trip_id, fare_id, amount, currency="EUR"):
    path = f"/trips/{trip_id}/fares/{fare_id}/price"
    return client.post(path, data={"price_amount": amount, "price_currency": currency,
                                   "csrf_token": _token(client, path)}, follow_redirects=False)


def test_change_price_reranks_and_keeps_history(client, engine, trip_id):
    fare_id = _store(engine, trip_id, "manual", "90.00")
    _store(engine, trip_id, "bahn.de", "88.00", LEGS2)
    page = client.get(f"/trips/{trip_id}").text
    assert f"/fares/{fare_id}/price" in page and "Change price" in page
    assert page.index("€88 price") < page.index("€90 price")
    form = client.get(f"/trips/{trip_id}/fares/{fare_id}/price")
    assert form.status_code == 200 and 'value="90.00"' in form.text
    r = _post(client, trip_id, fare_id, "85")
    assert r.status_code == 303
    page = client.get(f"/trips/{trip_id}").text
    assert page.index("€85 price") < page.index("€88 price")
    assert _prices(engine, fare_id) == [Decimal("90.00"), Decimal("85.00")]
    with Session(engine) as s:
        f = s.get(Fare, fare_id)
        assert f.latest_price == Decimal("85.00") and f.currency == "EUR"
        assert s.scalars(select(FarePrice).where(FarePrice.fare_id == fare_id)
                         .order_by(FarePrice.captured_at.desc())).first().capture_id is None
        it_id = f.itinerary_id
    hist = client.get(f"/trips/{trip_id}/itineraries/{it_id}/history").text
    assert "90" in hist and "85" in hist


@pytest.mark.parametrize("amount", ["", "-5", "abc"])
def test_bad_amount_is_422(client, engine, trip_id, amount):
    fare_id = _store(engine, trip_id, "manual", "90.00")
    r = _post(client, trip_id, fare_id, amount)
    assert r.status_code == 422 and 'class="errors"' in r.text and "price_amount" in r.text
    assert _prices(engine, fare_id) == [Decimal("90.00")]


def test_other_source_is_400_and_wrong_trip_404(client, engine, trip_id):
    fare_id = _store(engine, trip_id, "bahn.de", "90.00")
    assert client.get(f"/trips/{trip_id}/fares/{fare_id}/price").status_code == 400
    r = client.post(f"/trips/{trip_id}/fares/{fare_id}/price", follow_redirects=False,
                    data={"price_amount": "85", "price_currency": "EUR", "csrf_token": _token(client, f"/trips/{trip_id}/offers/new")})
    assert r.status_code == 400
    assert client.get(f"/trips/{trip_id}/fares/999999/price").status_code == 404
