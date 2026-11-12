"""The CO2 grams of a leg (#2586): the Trainline parser reads them, the ingest stores them, a later capture with a
value replaces them and one with no value keeps them; a negative value is rejected; the migration downgrades."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Leg, Trip
from app.parsers.trainline import TrainlineParser
from tests.test_ingest_api import BODY, setup  # noqa: F401
from app.schemas import IngestIn

T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
FIX = Path(__file__).parent / "fixtures" / "thetrainline.com" / "search-amsterdam-berlin.json"


def offer(co2=None):
    b = copy.deepcopy(BODY)
    b["trip_id"] = 1
    if co2 is not None:
        b["offers"][0]["legs"][0]["co2_g"] = co2
    return IngestIn(**b).offers[0]


def co2_of(sessions, trip_id):
    with sessions() as s:
        return s.scalar(select(Leg.co2_g).where(Leg.seq == 1, Leg.itinerary.has(trip_id=trip_id)))


def test_the_fixture_gives_the_co2_of_the_ice_legs():
    r = TrainlineParser().parse(json.loads(FIX.read_text(encoding="utf-8")))
    co2 = {leg.service_no: leg.co2_g for o in r.offers for leg in o.legs}
    assert co2["ICE 145"] == 10904
    assert co2["ICE 225"] == 3163
    assert co2["ICE 547"] == 8884


def test_the_ingest_stores_replaces_and_keeps_the_co2(sessions):
    with sessions() as s:
        trip = Trip(title="co2")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    for i, value in enumerate([900, 950, None]):
        with sessions() as s:
            upsert_offers(s, trip_id, None, [offer(value)], source="bahn.de", captured_at=T1.replace(day=8 + i))
            s.commit()
        assert co2_of(sessions, trip_id) == (900 if i == 0 else 950)


def test_a_negative_co2_rejects_the_offer(setup, sessions):  # noqa: F811
    """A bad offer is skipped with its reason, not a 422 of the whole body (`offer_errors`, as #2548)."""
    client, auth, trip_id = setup
    b = copy.deepcopy(BODY)
    b["trip_id"] = trip_id
    b["offers"][0]["legs"][0]["co2_g"] = -1
    assert client.post("/api/ingest", json=b, headers=auth).status_code == 200
    with sessions() as s:
        assert s.scalar(select(Leg.id)) is None
    assert [e["index"] for e in IngestIn(**b).offer_errors] == [0]


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
        assert "co2_g" in {c["name"] for c in inspect(engine).get_columns("legs")}
        command.downgrade(cfg, "0067")
        assert "co2_g" not in {c["name"] for c in inspect(engine).get_columns("legs")}
        command.upgrade(cfg, "head")
        assert "co2_g" in {c["name"] for c in inspect(engine).get_columns("legs")}
    finally:
        engine.dispose()


def test_the_parser_version_is_1_4_0():
    assert TrainlineParser.version == "1.4.0"
