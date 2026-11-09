"""The arrival delay of a booked journey and its EU rail claim (#1691)."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.auth import make_password_hash
from app.delay_claim import claim
from app.main import app
from app.models import Itinerary, Leg, Trip
from tests.test_trip_booked import _alembic, csrf

PASSWORD = "pw"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def journey(modes=("train",), price=Decimal("90.00"), delay=None, booked=True, days=-1, currency="EUR"):
    depart = NOW + timedelta(days=days)
    legs = [Leg(seq=i, mode=m, carrier="NS", service_no="1", from_name="A", to_name="B", depart_at=depart,
                depart_offset_min=60, arrive_at=depart + timedelta(hours=1), arrive_offset_min=60)
            for i, m in enumerate(modes)]
    return Itinerary(fingerprint=f"f{days}{booked}", depart_at=depart, arrive_at=depart + timedelta(hours=2),
                     duration_min=120, booked=booked, booked_price=price, booked_currency=currency,
                     delay_min=delay, legs=legs)


@pytest.mark.parametrize("delay,percent,amount", [(75, 25, "22.50"), (130, 50, "45.00"), (60, 25, "22.50"),
                                                  (120, 50, "45.00")])
def test_claim_percent_and_amount(delay, percent, amount):
    c = claim(journey(delay=delay))
    assert (c.percent, c.amount, c.currency) == (percent, Decimal(amount), "EUR")


def test_no_currency_is_eur_and_half_up():
    c = claim(journey(delay=61, price=Decimal("0.10"), currency=None))
    assert (c.amount, c.currency) == (Decimal("0.03"), "EUR")


@pytest.mark.parametrize("it", [journey(delay=59), journey(delay=40), journey(("train", "bus"), delay=130),
                                journey(("flight",), delay=130), journey(price=None, delay=130),
                                journey(delay=None), journey(delay=130, booked=False)])
def test_no_claim(it):
    assert claim(it) is None


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def add(sessions, **kw):
    with sessions() as s:
        trip = Trip(title="T", origin_text="A", destination_text="B", status="planning")
        trip.itineraries = [journey(**kw)]
        s.add(trip)
        s.commit()
        return trip.id, trip.itineraries[0].id


def stored(sessions, it_id):
    with sessions() as s:
        return s.get(Itinerary, it_id).delay_min


def post(client, ids, minutes):
    return client.post(f"/trips/{ids[0]}/itineraries/{ids[1]}/delay",
                       data={"minutes": minutes, "csrf_token": csrf(client, ids[0])}, follow_redirects=False)


def test_the_route_stores_and_clears(client, sessions):
    ids = add(sessions)
    assert post(client, ids, "75").status_code == 303
    assert stored(sessions, ids[1]) == 75
    assert post(client, ids, " ").status_code == 303
    assert stored(sessions, ids[1]) is None


@pytest.mark.parametrize("bad", ["-1", "1441", "abc", "7.5"])
def test_a_bad_value_is_422_and_stores_nothing(client, sessions, bad):
    ids = add(sessions, delay=30)
    assert post(client, ids, bad).status_code == 422
    assert stored(sessions, ids[1]) == 30


@pytest.mark.parametrize("kw", [{"days": 1}, {"booked": False}])
def test_not_arrived_or_not_booked_is_409(client, sessions, kw):
    ids = add(sessions, **kw)
    assert post(client, ids, "75").status_code == 409
    assert stored(sessions, ids[1]) is None


def test_migration_0036_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def cols():
            return {c["name"] for c in inspect(engine).get_columns("itineraries")}
        assert {"delay_min", "claim_paid_at"} <= cols()
        command.downgrade(cfg, "0035")
        assert not {"delay_min", "claim_paid_at"} & cols()
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
