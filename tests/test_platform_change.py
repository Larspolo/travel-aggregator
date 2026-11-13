"""A booked leg keeps the platform before its first change (#2683); the migration upgrades and downgrades."""

import copy
from datetime import UTC, datetime

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Itinerary, Leg, Trip
from app.schemas import IngestIn
from tests.test_ingest_api import BODY

T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)


def offer(platform=None):
    b = copy.deepcopy(BODY)
    b["trip_id"] = 1
    if platform is not None:
        b["offers"][0]["legs"][0]["from_platform"] = platform
    return IngestIn(**b).offers[0]


def run(sessions, values, booked):
    with sessions() as s:
        trip = Trip(title="platform change")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    out = []
    for day, value in enumerate(values):
        with sessions() as s:
            upsert_offers(s, trip_id, None, [offer(value)], source="bahn.de", captured_at=T1.replace(day=8 + day))
            if day == 0 and booked:
                s.scalar(select(Itinerary).where(Itinerary.trip_id == trip_id)).booked = True
            s.commit()
        with sessions() as s:
            leg = s.scalar(select(Leg).where(Leg.seq == 1, Leg.itinerary.has(trip_id=trip_id)))
            out.append((leg.from_platform, leg.booked_from_platform))
    return out


def test_a_booked_leg_keeps_the_first_platform(sessions):
    assert run(sessions, ["8b", "11", "12", None], True) == [
        ("8b", None), ("11", "8b"), ("12", "8b"), ("12", "8b")]


def test_no_platform_keeps_the_values_and_a_leg_not_booked_gets_no_booked_value(sessions):
    assert run(sessions, ["8b", None], True) == [("8b", None), ("8b", None)]
    assert run(sessions, ["8b", "11"], False) == [("8b", None), ("11", None)]


def test_the_migration_upgrades_and_downgrades_to_0074(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    new = {"booked_from_platform", "booked_to_platform"}
    try:
        cols = lambda: {c["name"] for c in inspect(engine).get_columns("legs")}  # noqa: E731
        assert new <= cols()
        command.downgrade(cfg, "0074")
        assert not new & cols()
        command.upgrade(cfg, "head")
        assert new <= cols()
    finally:
        engine.dispose()
