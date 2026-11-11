"""The cancel time of a booked journey (#2311)."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.auth import make_password_hash
from app.main import app
from app.models import Fare, Itinerary, Leg, Trip
from tests.test_trip_booked import _alembic, csrf

PASSWORD = "pw"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def add(sessions, booked=True, code=None, offset=60):
    with sessions() as s:
        trip = Trip(title="T", origin_text="A", destination_text="B", status="planning")
        trip.itineraries = [Itinerary(fingerprint="f", depart_at=NOW + timedelta(days=3),
                                      arrive_at=NOW + timedelta(days=3, hours=2), duration_min=120, booked=booked,
                                      booked_price=Decimal("50.00") if booked else None,
                                      booked_currency="EUR" if booked else None, booking_code=code,
                                      legs=[Leg(seq=0, mode="train", carrier="NS", service_no="1", from_name="A",
                                                to_name="B", depart_at=NOW + timedelta(days=3), depart_offset_min=offset,
                                                arrive_at=NOW + timedelta(days=3, hours=2), arrive_offset_min=60)])]
        Fare(itinerary=trip.itineraries[0], source="ns", latest_price=Decimal("50"), currency="EUR",
             latest_captured_at=NOW)
        s.add(trip)
        s.commit()
        return trip.id, trip.itineraries[0].id


def stored(sessions, it_id):
    with sessions() as s:
        it = s.get(Itinerary, it_id)
        return it.cancel_by, it.cancel_by_offset_min


def post(client, ids, value):
    return client.post(f"/trips/{ids[0]}/itineraries/{ids[1]}/cancel-by",
                       data={"cancel_by": value, "csrf_token": csrf(client, ids[0])}, follow_redirects=False)


def test_store_show_and_clear(client, sessions):
    ids = add(sessions)
    assert 'name="cancel_by"' in client.get(f"/trips/{ids[0]}").text
    assert post(client, ids, "2026-12-18T18:00").status_code == 303
    assert stored(sessions, ids[1]) == (datetime(2026, 12, 18, 17, 0, tzinfo=timezone.utc), 60)
    page = client.get(f"/trips/{ids[0]}").text
    assert "Cancel until 18 Dec 18:00" in page
    assert 'value="2026-12-18T18:00"' in page
    assert post(client, ids, "").status_code == 303
    assert stored(sessions, ids[1]) == (None, None)


def test_text_is_422_and_stores_nothing(client, sessions):
    ids = add(sessions)
    assert post(client, ids, "2026-12-18T18:00").status_code == 303
    assert post(client, ids, "tomorrow").status_code == 422
    assert stored(sessions, ids[1]) == (datetime(2026, 12, 18, 17, 0, tzinfo=timezone.utc), 60)


def test_not_booked_is_409_and_other_trip_is_404(client, sessions):
    ids = add(sessions, booked=False)
    assert post(client, ids, "2026-12-18T18:00").status_code == 409
    assert stored(sessions, ids[1]) == (None, None)
    other = add(sessions)
    assert post(client, (other[0], ids[1]), "2026-12-18T18:00").status_code == 404


def test_unbook_clears(client, sessions):
    ids = add(sessions)
    assert post(client, ids, "2026-12-18T18:00").status_code == 303
    r = client.post(f"/trips/{ids[0]}/itineraries/{ids[1]}/booked",
                    data={"csrf_token": csrf(client, ids[0])}, follow_redirects=False)
    assert r.status_code < 400
    assert stored(sessions, ids[1]) == (None, None)


def test_migration_0057_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def cols():
            return {c["name"] for c in inspect(engine).get_columns("itineraries")}
        assert {"cancel_by", "cancel_by_offset_min"} <= cols()
        command.downgrade(cfg, "0056")
        assert not {"cancel_by", "cancel_by_offset_min"} & cols()
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
