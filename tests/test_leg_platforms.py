"""The planned platforms of a leg (#2590): the bahn.de parser gives them, the ingest stores them, a later capture
with a value replaces them; a too long value is rejected; the migration upgrades and downgrades."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Leg, Trip
from app.parsers.bahn import BahnParser
from app.schemas import IngestIn
from tests.test_ingest_api import BODY, setup  # noqa: F401

T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-amsterdam-berlin.json"


def offer(platform=None):
    b = copy.deepcopy(BODY)
    b["trip_id"] = 1
    if platform is not None:
        b["offers"][0]["legs"][0]["from_platform"] = platform
    return IngestIn(**b).offers[0]


def platform_of(sessions, trip_id):
    with sessions() as s:
        return s.scalar(select(Leg.from_platform).where(Leg.seq == 1, Leg.itinerary.has(trip_id=trip_id)))


def test_the_fixture_gives_the_platforms_of_ice_141():
    legs = [leg for o in BahnParser().parse(json.loads(FIX.read_text(encoding="utf-8"))).offers for leg in o.legs]
    ice = [leg for leg in legs if leg.service_no == "ICE 141"]
    assert ice and all((leg.from_platform, leg.to_platform) == ("8b", "4") for leg in ice)


def test_a_leg_with_no_halte_gives_none():
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    for conn in raw.get("response", raw)["verbindungen"]:
        for a in conn["verbindungsAbschnitte"]:
            a.pop("halte", None)
    legs = [leg for o in BahnParser().parse(raw).offers for leg in o.legs]
    assert legs and all(leg.from_platform is None and leg.to_platform is None for leg in legs)


def test_a_later_capture_replaces_the_platform_and_no_value_keeps_it(sessions):
    with sessions() as s:
        trip = Trip(title="platforms")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    for value, at, expected in (("7", T1, "7"), ("8", T1.replace(day=9), "8"), (None, T1.replace(day=10), "8")):
        with sessions() as s:
            upsert_offers(s, trip_id, None, [offer(value)], source="bahn.de", captured_at=at)
            s.commit()
        assert platform_of(sessions, trip_id) == expected


def test_a_platform_of_11_characters_rejects_the_offer(setup):  # noqa: F811
    """A bad offer is rejected one by one (HTTP 200, `rejected`), as each other leg field (#2548)."""
    client, auth, trip_id = setup
    b = copy.deepcopy(BODY)
    b["trip_id"] = trip_id
    b["offers"][0]["legs"][0]["from_platform"] = "x" * 11
    r = client.post("/api/ingest", json=b, headers=auth)
    assert r.json()["rejected"] == 1 and r.json()["created"] == 0


def test_the_migration_upgrades_and_downgrades_to_0067(empty_database_url):
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
        assert {"from_platform", "to_platform"} <= cols()
        command.downgrade(cfg, "0067")
        assert not {"from_platform", "to_platform"} & cols()
        command.upgrade(cfg, "head")
        assert {"from_platform", "to_platform"} <= cols()
    finally:
        engine.dispose()
