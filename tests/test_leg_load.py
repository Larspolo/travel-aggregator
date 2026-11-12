"""The expected load of each class of a leg (#2582): the bahn.de parser gives it, the ingest stores it, a newer
capture with a value replaces it; the schema rejects a value out of 1 to 4; the migration upgrades and downgrades."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Leg, Trip
from app.parsers.bahn import BahnParser
from app.schemas import IngestIn
from tests.test_ingest_api import BODY, body, setup  # noqa: F401, F811 (the fixture)

T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
T2 = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen.json"


def legs_by_name(raw):
    return {leg.service_no: leg for o in BahnParser().parse(raw).offers for leg in o.legs}


def test_the_fixture_gives_the_load_of_ice_611_and_ice_519():
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    conns = raw["response"]["verbindungen"]
    conns[1]["angebotsPreis"] = conns[0]["angebotsPreis"]  # the ICE 611 connection has no price in the fixture
    legs = legs_by_name(raw)
    assert (legs["ICE 611"].load_first, legs["ICE 611"].load_second) == (3, 3)
    assert (legs["ICE 519"].load_first, legs["ICE 519"].load_second) == (None, 4)


def test_stufe_0_gives_none():
    assert legs_by_name(json.loads(FIX.read_text(encoding="utf-8")))["S12"].load_first is None
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    for conn in raw["response"]["verbindungen"]:
        for a in conn["verbindungsAbschnitte"]:
            a["auslastungsmeldungen"] = [{"klasse": "KLASSE_1", "stufe": 0}, {"klasse": "KLASSE_2", "stufe": 0}]
    legs = legs_by_name(raw)
    assert legs and all(leg.load_first is None and leg.load_second is None for leg in legs.values())


def offer(load_second=None):
    b = copy.deepcopy(BODY)
    b["trip_id"] = 1
    if load_second is not None:
        b["offers"][0]["legs"][0]["load_second"] = load_second
    return IngestIn(**b).offers[0]


def load_of(sessions, trip_id):
    with sessions() as s:
        return s.scalar(select(Leg.load_second).where(Leg.seq == 1, Leg.itinerary.has(trip_id=trip_id)))


def test_the_ingest_stores_the_load_and_a_newer_value_replaces_it(sessions):
    with sessions() as s:
        trip = Trip(title="load")
        s.add(trip)
        s.commit()
        trip_id = trip.id
        upsert_offers(s, trip_id, None, [offer(2)], source="bahn.de", captured_at=T1)
        s.commit()
    assert load_of(sessions, trip_id) == 2
    for at, value in ((T2, 3), (datetime(2026, 11, 10, 9, 0, tzinfo=UTC), None)):
        with sessions() as s:
            upsert_offers(s, trip_id, None, [offer(value)], source="bahn.de", captured_at=at)
            s.commit()
        assert load_of(sessions, trip_id) == 3


@pytest.mark.parametrize("value", [0, 5])
def test_the_ingest_rejects_a_load_out_of_range(setup, value):  # noqa: F811
    """The ingest rejects the offer (422 for a body with only this offer is not the design: each bad offer goes to
    `offer_errors`, as for a bad service, #2548)."""
    client, auth, trip_id = setup
    b = body(trip_id)
    b["offers"][0]["legs"][0]["load_second"] = value
    r = client.post("/api/ingest", json=b, headers=auth)
    assert r.status_code == 200
    assert IngestIn(**b).offers == [] and [e["index"] for e in IngestIn(**b).offer_errors] == [0]


def test_the_migration_upgrades_and_downgrades_to_0066(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def columns():
            return {c["name"] for c in inspect(engine).get_columns("legs")}
        assert {"load_first", "load_second"} <= columns()
        command.downgrade(cfg, "0066")
        assert not {"load_first", "load_second"} & columns()
        command.upgrade(cfg, "head")
        assert {"load_first", "load_second"} <= columns()
    finally:
        engine.dispose()
