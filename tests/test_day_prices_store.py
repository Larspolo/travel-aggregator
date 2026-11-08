"""The ingest stores the day prices of a capture (#1197): one row per source, trip and day, the newest price wins,
a reparse gives the same rows, and the migration 0026 upgrades and downgrades."""

import copy
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect, select, text

from app import ingest
from app.models import Capture, DayPrice
from tests.test_bahn_ingest import body, setup  # noqa: F401 (fixture)
from tests.test_trip_booked import _alembic

FIX = Path(__file__).parent / "fixtures" / "bahn.de"
FIRST = "tagesbestpreis-amsterdam-zuerich-2026-12-01.json"


def _raw(name=FIRST):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _rows(sessions, trip_id):
    with sessions() as s:
        return [(r.source, r.day, r.price, r.currency) for r in
                s.scalars(select(DayPrice).where(DayPrice.trip_id == trip_id).order_by(DayPrice.day))]


def _with_price(raw, amount):
    raw = copy.deepcopy(raw)
    for interval in raw["response"]["intervalle"]:
        interval["preis"]["betrag"] = amount
    return raw


def test_an_ingest_stores_one_row_per_day_as_decimal(setup, sessions):  # noqa: F811
    client, auth, trip_id = setup
    r = client.post("/api/ingest", json=body(trip_id, _raw()), headers=auth)
    assert r.status_code == 200, r.text
    rows = _rows(sessions, trip_id)
    assert rows == [("bahn.de", date(2026, 12, 1), Decimal("49.99"), "EUR")]
    assert isinstance(rows[0][2], Decimal)


def test_a_later_capture_replaces_the_price_of_the_day(setup, sessions):  # noqa: F811
    client, auth, trip_id = setup
    client.post("/api/ingest", json=body(trip_id, _raw()), headers=auth)
    later = body(trip_id, _with_price(_raw(), 59.5), captured_at="2026-11-04T10:00:00Z")
    assert client.post("/api/ingest", json=later, headers=auth).status_code == 200
    assert _rows(sessions, trip_id) == [("bahn.de", date(2026, 12, 1), Decimal("59.50"), "EUR")]
    older = body(trip_id, _with_price(_raw(), 10), captured_at="2026-11-01T10:00:00Z")
    client.post("/api/ingest", json=older, headers=auth)
    assert _rows(sessions, trip_id)[0][2] == Decimal("59.50")


def test_a_reparse_gives_the_same_rows(setup, sessions):  # noqa: F811
    client, auth, trip_id = setup
    client.post("/api/ingest", json=body(trip_id, _raw()), headers=auth)
    before = _rows(sessions, trip_id)
    with sessions() as s:
        s.execute(text("DELETE FROM day_prices"))
        s.commit()
        capture = s.scalar(select(Capture).where(Capture.trip_id == trip_id))
        ingest.reparse(s, capture)
        ingest.reparse(s, capture)
    assert _rows(sessions, trip_id) == before


def test_the_migration_upgrades_and_downgrades_with_rows(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        command.downgrade(cfg, "0025")
        assert "day_prices" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "head")
        with engine.begin() as c:
            trip_id = c.execute(text("INSERT INTO trips (title) VALUES ('T') RETURNING id")).scalar()
            c.execute(text("INSERT INTO day_prices (source, trip_id, day, price, currency, captured_at) "
                           "VALUES ('bahn.de', :t, '2026-12-01', 49.99, 'EUR', now())"), {"t": trip_id})
        command.downgrade(cfg, "0025")
        assert "day_prices" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "head")
        assert "day_prices" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
