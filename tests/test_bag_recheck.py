"""The bag recheck of a kiwi.com transfer (#2660): the parser gives it, the ingest stores it, a later capture with
another value replaces it; the migration upgrades and downgrades."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Leg, Trip
from app.parsers.kiwi import KiwiParser
from app.schemas import IngestIn
from tests.test_ingest_api import BODY

T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
FIX = Path(__file__).parent / "fixtures" / "kiwi.com" / "search-amsterdam-lisbon.json"


def test_the_fixture_gives_the_bag_recheck_of_each_transfer():
    offers = KiwiParser().parse(json.loads(FIX.read_text(encoding="utf-8"))).offers
    by_route = {(leg.from_code, leg.to_code): leg.bag_recheck for o in offers for leg in o.legs[1:]}
    assert by_route[("OPO", "LIS")] is True
    assert by_route[("MAD", "LIS")] is False
    assert all(o.legs[0].bag_recheck is None for o in offers)


def offer(value):
    b = copy.deepcopy(BODY)
    b["trip_id"] = 1
    b["offers"][0]["legs"][0]["bag_recheck"] = value
    return IngestIn(**b).offers[0]


def test_a_later_capture_replaces_the_value_and_none_keeps_it(sessions):
    with sessions() as s:
        trip = Trip(title="recheck")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    for value, at, expected in ((True, T1, True), (False, T1.replace(day=9), False), (None, T1.replace(day=10), False)):
        with sessions() as s:
            upsert_offers(s, trip_id, None, [offer(value)], source="bahn.de", captured_at=at)
            s.commit()
        with sessions() as s:
            got = s.scalar(select(Leg.bag_recheck).where(Leg.seq == 1, Leg.itinerary.has(trip_id=trip_id)))
        assert got is expected


def test_the_migration_upgrades_and_downgrades_to_0072(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        cols = lambda: {c["name"] for c in inspect(engine).get_columns("legs")}  # noqa: E731
        assert "bag_recheck" in cols()
        command.downgrade(cfg, "0072")
        assert "bag_recheck" not in cols()
        command.upgrade(cfg, "head")
        assert "bag_recheck" in cols()
    finally:
        engine.dispose()
