"""The on-board services of a leg (#2548): the FlixBus parser gives them, the ingest stores them, a later capture
of the same itinerary replaces them; the schema keeps only a known value; the migration upgrades and downgrades."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Leg, Trip
from app.parsers.flixbus import FlixbusParser
from app.schemas import IngestIn
from tests.test_ingest_api import BODY

T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
T2 = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
FIX = Path(__file__).parent / "fixtures" / "flixbus.com" / "search-amsterdam-paris.json"


def offer(services=None, **update):
    b = copy.deepcopy(BODY)
    b["trip_id"] = 1
    o = b["offers"][0]
    o.update(update)
    if services is not None:
        o["legs"][0]["services"] = services
    return IngestIn(**b).offers[0]


def store(sessions, offers, at):
    with sessions() as s:
        trip = Trip(title="services")
        s.add(trip)
        s.commit()
        upsert_offers(s, trip.id, None, offers, source="bahn.de", captured_at=at)
        s.commit()
        return trip.id


def services_of(sessions, trip_id):
    with sessions() as s:
        return s.scalar(select(Leg.services).where(Leg.seq == 1, Leg.itinerary.has(trip_id=trip_id)))


def test_the_fixture_gives_wifi_and_power():
    r = FlixbusParser().parse(json.loads(FIX.read_text(encoding="utf-8")))
    assert {tuple(leg.services) for o in r.offers for leg in o.legs} == {("wifi", "power")}


def test_only_a_toilet_gives_no_services():
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    for trip in raw["response"]["trips"]:
        for conn in trip["results"].values() if isinstance(trip["results"], dict) else trip["results"]:
            for leg in conn["legs"]:
                leg["amenities"] = ["TOILET"]
    r = FlixbusParser().parse(raw)
    assert r.offers and all(leg.services == [] for o in r.offers for leg in o.legs)


def test_the_ingest_stores_wifi_and_a_later_capture_replaces_it(sessions):
    trip_id = store(sessions, [offer(["wifi"])], T1)
    assert services_of(sessions, trip_id) == "wifi"
    with sessions() as s:
        upsert_offers(s, trip_id, None, [offer(["wifi", "power"])], source="bahn.de", captured_at=T2)
        s.commit()
    assert services_of(sessions, trip_id) == "wifi,power"


def test_an_offer_without_services_stores_none(sessions):
    assert services_of(sessions, store(sessions, [offer()], T1)) is None


def test_the_schema_rejects_an_unknown_service():
    b = copy.deepcopy(BODY)
    b["trip_id"] = 1
    b["offers"][0]["legs"][0]["services"] = ["toilet"]
    body = IngestIn(**b)
    assert body.offers == []
    assert [e["index"] for e in body.offer_errors] == [0]


def test_the_migration_upgrades_and_downgrades_to_0065(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        assert "services" in {c["name"] for c in inspect(engine).get_columns("legs")}
        command.downgrade(cfg, "0065")
        assert "services" not in {c["name"] for c in inspect(engine).get_columns("legs")}
        command.upgrade(cfg, "head")
        assert "services" in {c["name"] for c in inspect(engine).get_columns("legs")}
    finally:
        engine.dispose()
