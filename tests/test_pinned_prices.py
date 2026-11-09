"""The Pinned page shows the lowest price of the cheapest fare and the drop since the last view (#1300)."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.auth import make_password_hash
from app.main import app
from app.models import Fare, FarePrice, Itinerary, Leg, Trip

PASSWORD = "pw"
SOON = datetime.now(timezone.utc).replace(hour=7, minute=12, second=0, microsecond=0) + timedelta(days=10)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def add_pinned(s, title, latest, prices=(), seen=None, depart=SOON):
    trip = Trip(title=title, origin_text="A", destination_text="B", status="planning")
    leg = Leg(seq=0, mode="train", carrier="NS", service_no="IC 1", from_name="Amsterdam", to_name="Berlin",
              depart_at=depart, depart_offset_min=60, arrive_at=depart + timedelta(hours=2), arrive_offset_min=60)
    it = Itinerary(fingerprint=title, depart_at=depart, arrive_at=depart + timedelta(hours=2), duration_min=120,
                   pinned=True, hidden=False, legs=[leg])
    fare = Fare(source="bahn", latest_price=Decimal(latest), currency="EUR", latest_captured_at=depart,
                seen_price=None if seen is None else Decimal(seen))
    fare.prices = [FarePrice(price=Decimal(p), currency="EUR", captured_at=depart) for p in prices]
    it.fares = [fare]
    trip.itineraries = [it]
    s.add(trip)
    s.commit()


def test_lowest_price_shown_when_current_price_is_above_it(client, sessions):
    with sessions() as s:
        add_pinned(s, "Above trip", latest="90", prices=("90", "78", "90"))
    html = client.get("/pinned").text
    assert "lowest €78.00, now €12.00 above" in html


def test_fare_at_its_lowest_says_so(client, sessions):
    with sessions() as s:
        add_pinned(s, "Lowest trip", latest="78", prices=("90", "78"))
    html = client.get("/pinned").text
    assert "at its lowest" in html
    assert "lowest €" not in html


def test_drop_since_last_view_is_shown(client, sessions):
    with sessions() as s:
        add_pinned(s, "Dropped trip", latest="90", prices=("95", "90"), seen="95")
    html = client.get("/pinned").text
    assert "price dropped €5.00" in html


def test_no_drop_text_without_a_seen_price(client, sessions):
    with sessions() as s:
        add_pinned(s, "Unseen trip", latest="90", prices=("90",), seen=None)
    html = client.get("/pinned").text
    assert "price dropped" not in html


def count_queries(client):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        response = client.get("/pinned")
    finally:
        event.remove(Engine, "before_cursor_execute", record)
    assert response.status_code == 200
    return len(statements)


def test_query_count_does_not_grow_with_rows(client, sessions):
    with sessions() as s:
        add_pinned(s, "Row 0", latest="90", prices=("90", "78"), seen="95")
    one = count_queries(client)
    assert one > 0
    with sessions() as s:
        for i in range(1, 20):
            add_pinned(s, f"Row {i}", latest="90", prices=("90", "78"), seen="95", depart=SOON + timedelta(hours=i))
    twenty = count_queries(client)
    assert one == twenty
