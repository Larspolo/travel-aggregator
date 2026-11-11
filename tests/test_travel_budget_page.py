"""The page "Travel per year" has a budget per year and shows the rest or the sum over it (#2375)."""

import re
from datetime import datetime, timezone
from decimal import Decimal

from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select

from app.main import app
from app.models import Itinerary, TravelBudget
from tests.test_spend_page import add, client, text  # noqa: F401
from tests.test_trip_booked import _alembic


def _csrf(c):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get("/upcoming/years").text).group(1)


def _post(c, amount, year=2026):
    return c.post(f"/upcoming/years/{year}/budget", data={"amount": amount, "csrf_token": _csrf(c)},
                  follow_redirects=False)


def _journeys(sessions):
    with sessions() as s:
        add(s, 0, 2026, "train", 600, "1000.00")
        add(s, 1, 2026, "bus", 60, "15.80")
        s.commit()


def test_budget_left_over_and_removed(client, sessions):  # noqa: F811
    _journeys(sessions)
    assert _post(client, "1200").status_code == 303
    assert "€1,015.80 of €1,200.00 · €184.20 left" in text(client.get("/upcoming/years").text)
    assert _post(client, "900").status_code == 303
    assert "€115.80 over the budget" in text(client.get("/upcoming/years").text)
    assert _post(client, "").status_code == 303
    page = text(client.get("/upcoming/years").text)
    assert "left" not in page and "over the budget" not in page
    with sessions() as s:
        assert s.scalars(select(TravelBudget)).all() == []


def test_cancelled_booking_counts_paid_less_refund(client, sessions):  # noqa: F811
    _journeys(sessions)
    with sessions() as s:
        add(s, 2, 2026, "train", 60, "100.00")
        it = s.scalars(select(Itinerary).where(Itinerary.fingerprint == "f2026-2")).one()
        it.booked, it.cancelled_at, it.refund_price = False, datetime(2026, 2, 1, tzinfo=timezone.utc), Decimal("80")
        s.commit()
    _post(client, "1200")
    assert "€1,035.80 of €1,200.00 · €164.20 left" in text(client.get("/upcoming/years").text)


def test_bad_amounts_store_nothing(client, sessions):  # noqa: F811
    _journeys(sessions)
    for bad in ("-1", "1000001", "1.234", "abc"):
        r = _post(client, bad)
        assert r.status_code == 422 and "at most 2 decimals" in r.text
    with sessions() as s:
        assert s.scalars(select(TravelBudget)).all() == []


def test_post_needs_login_and_csrf(client, sessions):  # noqa: F811
    r = TestClient(app).post("/upcoming/years/2026/budget", data={"amount": "5"}, follow_redirects=False)
    assert r.status_code in (302, 303, 401, 403)
    r = client.post("/upcoming/years/2026/budget", data={"amount": "5", "csrf_token": "x"}, follow_redirects=False)
    assert r.status_code in (400, 403)
    with sessions() as s:
        assert s.scalars(select(TravelBudget)).all() == []


def test_migration_0059_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        assert "travel_budgets" in inspect(engine).get_table_names()
        command.downgrade(cfg, "0058")
        assert "travel_budgets" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
