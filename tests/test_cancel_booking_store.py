"""The cancel of a booked journey stores its refund and keeps the paid price (#1685)."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.auth import make_password_hash
from app.booked_overlap import conflicts
from app.calendar_feed import new_feed_token
from app.main import app
from app.models import Itinerary, Leg, Setting, Trip
from app.travel_day import TRAVEL_DAY_HOURS_KEY, due_travel_days

PASSWORD = "pw"
SOON = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=10)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def _add(sessions, title="One", price=Decimal("89"), booked=True):
    leg = Leg(seq=0, mode="train", carrier="NS", service_no="IC 777", from_name="A", to_name="B",
              depart_at=SOON, depart_offset_min=60, arrive_at=SOON + timedelta(hours=2), arrive_offset_min=60)
    trip = Trip(title=title, origin_text="A", destination_text="B", status="planning", date_from=SOON.date())
    it = Itinerary(fingerprint=title, depart_at=SOON, arrive_at=SOON + timedelta(hours=2), duration_min=120,
                   booked=booked, booked_price=price, booked_currency="EUR" if price is not None else None,
                   booked_at=SOON - timedelta(days=5), legs=[leg])
    trip.itineraries = [it]
    with sessions() as s:
        s.add(trip)
        s.commit()
        return trip.id, it.id


def _cancel(client, trip_id, it_id, refund=None):
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)
    data = {"csrf_token": token}
    if refund is not None:
        data["refund"] = refund
    return client.post(f"/trips/{trip_id}/itineraries/{it_id}/cancel", data=data, follow_redirects=False)


def test_a_cancel_keeps_the_paid_price_and_stores_the_refund(client, sessions):
    tid, iid = _add(sessions)
    assert _cancel(client, tid, iid, "60").status_code == 303
    with sessions() as s:
        it = s.get(Itinerary, iid)
        assert it.booked is False and it.refund_price == Decimal("60") and it.booked_price == Decimal("89")
        assert it.booked_currency == "EUR" and it.booked_at is not None and it.cancelled_at is not None


def test_a_blank_refund_stores_zero(client, sessions):
    tid, iid = _add(sessions)
    assert _cancel(client, tid, iid, "").status_code == 303
    with sessions() as s:
        assert s.get(Itinerary, iid).refund_price == Decimal("0")


@pytest.mark.parametrize("refund", ["-1", "89.01", "1.234", "abc", "nan"])
def test_a_bad_refund_is_422_and_stores_nothing(client, sessions, refund):
    tid, iid = _add(sessions)
    assert _cancel(client, tid, iid, refund).status_code == 422
    with sessions() as s:
        it = s.get(Itinerary, iid)
        assert it.booked is True and it.refund_price is None and it.cancelled_at is None


def test_with_no_paid_price_only_zero_is_valid(client, sessions):
    tid, iid = _add(sessions, price=None)
    assert _cancel(client, tid, iid, "1").status_code == 422
    assert _cancel(client, tid, iid, "0").status_code == 303


def test_not_booked_is_409_and_another_trip_is_404(client, sessions):
    tid, iid = _add(sessions, booked=False)
    assert _cancel(client, tid, iid, "0").status_code == 409
    other, _ = _add(sessions, title="Two")
    assert _cancel(client, other, iid, "0").status_code == 404


def test_a_cancelled_journey_is_on_no_list_of_booked_journeys(client, sessions):
    tid, iid = _add(sessions)
    _add(sessions, title="Two")  # the same time: a conflict before the cancel
    with sessions() as s:
        s.merge(Setting(key=TRAVEL_DAY_HOURS_KEY, value="24"))
        token = new_feed_token(s)
        s.commit()
        assert iid in conflicts(s, datetime.now(timezone.utc))
        assert iid in [it.id for it in due_travel_days(s, datetime.now(timezone.utc))]
    assert "IC 777" in TestClient(app).get(f"/calendar/{token}.ics").text
    assert _cancel(client, tid, iid, "60").status_code == 303
    with sessions() as s:
        assert iid not in conflicts(s, datetime.now(timezone.utc))
        assert iid not in [it.id for it in due_travel_days(s, datetime.now(timezone.utc))]
    assert TestClient(app).get(f"/calendar/{token}.ics").text.count("BEGIN:VEVENT") == 1
    assert client.get("/upcoming").text.count("IC 777") == 1


def test_a_new_booking_clears_the_cancel(client, sessions):
    tid, iid = _add(sessions)
    _cancel(client, tid, iid, "60")
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{tid}").text).group(1)
    client.post(f"/trips/{tid}/itineraries/{iid}/booked", data={"csrf_token": token}, follow_redirects=False)
    with sessions() as s:
        it = s.get(Itinerary, iid)
        assert it.booked is True and it.cancelled_at is None and it.refund_price is None


def test_the_migration_downgrades_and_upgrades(empty_database_url):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0034")
    eng = create_engine(empty_database_url)
    cols = {c["name"] for c in inspect(eng).get_columns("itineraries")}
    assert "cancelled_at" not in cols and "refund_price" not in cols
    command.upgrade(cfg, "head")
    cols = {c["name"] for c in inspect(eng).get_columns("itineraries")}
    assert {"cancelled_at", "refund_price"} <= cols
    eng.dispose()
