"""The notices of the operator (#2624): the bahn.de parser gives them, the ingest stores them, a later capture with
`[]` removes them and one with no `notices` keeps them; a too long text is rejected; the migration works."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Itinerary, Trip
from app.parsers.bahn import BahnParser
from app.schemas import IngestIn
from tests.test_ingest_api import BODY, setup  # noqa: F401

T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen.json"
NOTICE = {"text": "Track repairs", "level": "high", "leg": 0}


def test_the_fixture_gives_the_notices_of_ice_519():
    offers = BahnParser().parse(json.loads(FIX.read_text(encoding="utf-8"))).offers
    by_conn = {}
    for o in offers:
        by_conn.setdefault(o.legs[0].depart_at, o)
    conns = sorted(by_conn.values(), key=lambda o: o.legs[0].depart_at)
    first = next(o for o in conns if any(leg.service_no == "ICE 519" for leg in o.legs))
    ice = next(i for i, leg in enumerate(first.legs) if leg.service_no == "ICE 519")
    got = [(n.text, n.level, n.leg) for n in first.notices]
    assert got == [("All seats are already fully booked (1st class)", "high", ice), ("Track repairs", "high", ice)]
    last = next(o for o in conns if o.legs[0].service_no == "IC 2048")
    assert last.notices == []


def offer(notices="absent"):
    b = copy.deepcopy(BODY)
    b["trip_id"] = 1
    if notices != "absent":
        b["offers"][0]["notices"] = notices
    return IngestIn(**b).offers[0]


def test_a_capture_stores_removes_and_keeps_the_notices(sessions):
    with sessions() as s:
        trip = Trip(title="notices")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    steps = (([NOTICE], T1, [NOTICE]), ("absent", T1.replace(day=9), [NOTICE]), ([], T1.replace(day=10), []))
    for value, at, expected in steps:
        with sessions() as s:
            upsert_offers(s, trip_id, None, [offer(value)], source="bahn.de", captured_at=at)
            s.commit()
        with sessions() as s:
            assert s.scalar(select(Itinerary.notices).where(Itinerary.trip_id == trip_id)) == expected


def test_a_text_of_301_characters_rejects_the_offer(setup):  # noqa: F811
    client, auth, trip_id = setup
    b = copy.deepcopy(BODY)
    b["trip_id"] = trip_id
    b["offers"][0]["notices"] = [{"text": "x" * 301, "level": "low", "leg": None}]
    r = client.post("/api/ingest", json=b, headers=auth)
    # a bad offer is rejected one by one (HTTP 200, `rejected`), as each other offer field (#2548)
    assert r.json()["rejected"] == 1 and r.json()["created"] == 0


def test_the_migration_upgrades_and_downgrades_to_0069(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        cols = lambda: {c["name"] for c in inspect(engine).get_columns("itineraries")}  # noqa: E731
        assert "notices" in cols()
        command.downgrade(cfg, "0069")
        assert "notices" not in cols()
        command.upgrade(cfg, "head")
        assert "notices" in cols()
    finally:
        engine.dispose()
