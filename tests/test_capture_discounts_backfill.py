"""Migration 0079 fills the discount cards of old captures from their raw payloads (#2807)."""

import gzip
import json
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, text

from tests.test_trip_booked import _alembic

FIXTURES = Path(__file__).parent / "fixtures" / "bahn.de"


def _add(conn, trip_id, path):
    raw = gzip.compress(path.read_bytes()) if path else None
    return conn.execute(text("INSERT INTO captures (trip_id, source, raw_gz, captured_at) "
                             "VALUES (:t, 'bahn.de', :r, now()) RETURNING id"), {"t": trip_id, "r": raw}).scalar()


def test_the_migration_fills_null_cards_from_the_raw(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "0078")
    eng = create_engine(empty_database_url)
    with eng.begin() as conn:
        trip = conn.execute(text("INSERT INTO trips (title) VALUES ('old') RETURNING id")).scalar()
        no_card = _add(conn, trip, FIXTURES / "fahrplan-koeln-muenchen.json")
        card = _add(conn, trip, FIXTURES / "fahrplan-koeln-muenchen-bahncard25.json")
        no_raw = _add(conn, trip, None)
    command.upgrade(cfg, "0079")
    with eng.connect() as conn:
        got = dict(conn.execute(text("SELECT id, discounts FROM captures")).all())
    assert got[no_card] == []
    assert got[card] == ["BahnCard 25"]
    assert got[no_raw] is None
    command.downgrade(cfg, "0078")
    command.upgrade(cfg, "head")
    eng.dispose()
