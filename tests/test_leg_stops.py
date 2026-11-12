"""The stops of a leg (#2634): the bahn.de parser gives them, the ingest stores them, a later capture with stops
replaces them and one with None keeps them; 81 stops are rejected; the migration upgrades and downgrades."""

import copy
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Leg, LegStop, Trip
from app.parsers.bahn import BahnParser
from app.schemas import IngestIn
from tests.test_ingest_api import BODY, setup  # noqa: F401

T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-amsterdam-berlin.json"


def offer(names=None):
    b = copy.deepcopy(BODY)
    b["trip_id"] = 1
    if names is not None:
        b["offers"][0]["legs"][0]["stops"] = [{"name": n} for n in names]
    return IngestIn(**b).offers[0]


def stops_of(sessions, trip_id):
    with sessions() as s:
        leg = s.scalar(select(Leg).where(Leg.seq == 1, Leg.itinerary.has(trip_id=trip_id)))
        return [x.name for x in leg.stops]


def test_the_fixture_gives_the_stops_of_ice_141():
    legs = [leg for o in BahnParser().parse(json.loads(FIX.read_text(encoding="utf-8"))).offers for leg in o.legs]
    ice = [leg for leg in legs if leg.service_no == "ICE 141"]
    assert ice
    for leg in ice:
        assert len(leg.stops) == 12
        first = leg.stops[0]
        plus1 = timezone(timedelta(hours=1))
        assert first.name == "Hilversum" and first.platform == "3"
        assert first.arrive_at == datetime(2026, 12, 8, 6, 20, tzinfo=plus1)
        assert first.depart_at == datetime(2026, 12, 8, 6, 22, tzinfo=plus1)
        assert not {"Amsterdam Centraal", "Berlin Hbf"} & {x.name for x in leg.stops}


def test_a_leg_with_no_halte_gives_none():
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    for conn in raw.get("response", raw)["verbindungen"]:
        for a in conn["verbindungsAbschnitte"]:
            a.pop("halte", None)
    legs = [leg for o in BahnParser().parse(raw).offers for leg in o.legs]
    assert legs and all(leg.stops is None for leg in legs)


def test_a_capture_replaces_the_stops_and_none_keeps_them(sessions):
    with sessions() as s:
        trip = Trip(title="stops")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    for names, at, expected in ((["A", "B"], T1, ["A", "B"]), (["C"], T1.replace(day=9), ["C"]),
                                (None, T1.replace(day=10), ["C"])):
        with sessions() as s:
            upsert_offers(s, trip_id, None, [offer(names)], source="bahn.de", captured_at=at)
            s.commit()
        assert stops_of(sessions, trip_id) == expected
    with sessions() as s:
        assert s.scalar(select(LegStop.seq).where(LegStop.name == "C")) == 1
        assert s.scalar(select(LegStop).where(LegStop.name == "A")) is None


def test_81_stops_reject_the_offer(setup):  # noqa: F811
    """A bad offer is rejected one by one (HTTP 200, `rejected`), as each other leg field (#2548)."""
    client, auth, trip_id = setup
    b = copy.deepcopy(BODY)
    b["trip_id"] = trip_id
    b["offers"][0]["legs"][0]["stops"] = [{"name": f"S{k}"} for k in range(81)]
    r = client.post("/api/ingest", json=b, headers=auth)
    assert r.json()["rejected"] == 1 and r.json()["created"] == 0


def test_the_migration_upgrades_and_downgrades_to_0070(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        tables = lambda: set(inspect(engine).get_table_names())  # noqa: E731
        assert "leg_stops" in tables()
        command.downgrade(cfg, "0070")
        assert "leg_stops" not in tables()
        command.upgrade(cfg, "head")
        assert "leg_stops" in tables()
    finally:
        engine.dispose()
