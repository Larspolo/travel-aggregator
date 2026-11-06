"""The trips list page (#21)."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.auth import make_password_hash
from app.main import app
from app.models import Base, Fare, Itinerary, Trip
from app.trips import list_trips

PASSWORD = "pw"
T = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine(empty_database_url):
    engine = create_engine(empty_database_url)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _offer(trip: Trip, fp: str, *prices: str) -> Itinerary:
    it = Itinerary(trip=trip, fingerprint=fp, depart_at=T, arrive_at=T, duration_min=60)
    for p in prices:
        it.fares.append(Fare(source="x", latest_price=Decimal(p), currency="EUR", latest_captured_at=T))
    return it


def _seed(engine):
    with Session(engine) as s:
        a = Trip(title="Berlin", origin_text="Utrecht", destination_text="Berlin",
                 date_from=date(2026, 12, 1), date_to=date(2026, 12, 5))
        b = Trip(title="<script>alert(1)</script>", origin_text="A", destination_text="B")
        s.add_all([a, b, _offer(a, "f1", "89.90", "120.00"), _offer(a, "f2", "45.50")])
        s.commit()


def test_query_one_statement(engine):
    _seed(engine)
    statements = []
    event.listen(engine, "before_cursor_execute", lambda *a: statements.append(a[2]))
    with Session(engine) as s:
        rows = list_trips(s)
    assert len(statements) == 1
    by_title = {r.title: r for r in rows}
    berlin = by_title["Berlin"]
    assert berlin.offer_count == 2
    assert berlin.best_price == Decimal("45.50") and isinstance(berlin.best_price, Decimal)
    empty = by_title["<script>alert(1)</script>"]
    assert empty.offer_count == 0 and empty.best_price is None


def _client(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD})
    return c


def test_page(engine, empty_database_url, monkeypatch):
    _seed(engine)
    html = _client(monkeypatch, empty_database_url).get("/").text
    assert "Utrecht → Berlin" in html and "2026-12-01 – 2026-12-05" in html
    assert "EUR 45.50" in html and "active" in html
    assert "no offers yet" in html and "<td>0</td>" in html
    assert "<script>alert" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_empty_list(engine, empty_database_url, monkeypatch):
    html = _client(monkeypatch, empty_database_url).get("/").text
    assert 'href="/trips/new"' in html and "<table>" not in html
