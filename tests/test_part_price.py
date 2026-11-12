"""The part price of a bahn.de fare (#2655): the parser reads `hasTeilpreis`, the ingest stores it, a newer capture
updates it; the migration upgrades and downgrades to a named revision."""

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Fare, Trip
from app.parsers.bahn import BahnParser

FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen.json"
T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
T2 = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)


def raw(first: bool):
    r = json.loads(FIX.read_text(encoding="utf-8"))
    r["response"]["verbindungen"][0]["hasTeilpreis"] = first
    return r


def test_the_parser_marks_only_the_connection_with_a_part_price():
    r = raw(True)
    ids = [c.get("tripId") for c in r["response"]["verbindungen"]]
    offers = BahnParser().parse(r).offers
    assert offers
    for o in offers:
        assert o.part_price is (o.external_id == ids[0])
    assert any(o.part_price for o in offers) and not all(o.part_price for o in offers)


def _fares(sessions, trip_id):
    with sessions() as s:
        return sorted(s.scalars(select(Fare.part_price).where(Fare.itinerary.has(trip_id=trip_id))))


def test_the_ingest_stores_the_mark_and_a_newer_capture_removes_it(sessions):
    offers = BahnParser().parse(raw(True)).offers
    with sessions() as s:
        trip = Trip(title="part")
        s.add(trip)
        s.commit()
        trip_id = trip.id
        upsert_offers(s, trip_id, None, offers, source="bahn.de", captured_at=T1)
        s.commit()
    assert True in _fares(sessions, trip_id)
    with sessions() as s:
        upsert_offers(s, trip_id, None, BahnParser().parse(raw(False)).offers, source="bahn.de", captured_at=T2)
        s.commit()
    assert True not in _fares(sessions, trip_id)


def test_the_migration_upgrades_and_downgrades_to_0072(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0073")
    engine = create_engine(empty_database_url)
    try:
        assert "part_price" in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.downgrade(cfg, "0072")
        assert "part_price" not in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.upgrade(cfg, "head")
        assert "part_price" in {c["name"] for c in inspect(engine).get_columns("fares")}
    finally:
        engine.dispose()
