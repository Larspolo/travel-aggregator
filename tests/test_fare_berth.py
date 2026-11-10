"""The berth of a night-train fare (#1807): the ÖBB tiers give seat, couchette and sleeper; a bahn.de fare gives none;
the ingest stores it and updates it; the export and the import keep it; the migration upgrades and downgrades."""

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Fare, Trip
from app.parsers import get_parser
from app.parsers.oebb import OebbParser
from app.trip_import import import_trip
from app.web.export import load_trip, trip_export

FIX = Path(__file__).parent / "fixtures"
CAPTURED = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)


def load(source, name):
    return json.loads((FIX / source / name).read_text(encoding="utf-8"))


def nightjet_offers():
    return OebbParser().parse(load("oebbtickets.at", "fares-amsterdam-wien-nightjet.json")).offers


def test_the_nightjet_tiers_give_seat_couchette_and_sleeper():
    offers = nightjet_offers()
    assert [(o.fare_name, o.berth) for o in offers] == [
        ("Seat", "seat"), ("Couchette", "couchette"), ("Sleeper", "sleeper"),
    ]


def test_a_bahn_fare_has_no_berth():
    offers = get_parser("bahn.de").parse(load("bahn.de", "fahrplan-amsterdam-bern-night.json")).offers
    assert offers
    assert all(o.berth is None for o in offers)


def test_the_ingest_stores_the_berth_and_a_new_berth_updates_the_fare(sessions):
    offers = nightjet_offers()
    with sessions() as s:
        trip = Trip(title="berth")
        s.add(trip)
        s.commit()
        trip_id = trip.id
        upsert_offers(s, trip_id, None, offers, source="oebbtickets.at", captured_at=CAPTURED)
        s.commit()
        seat = s.scalar(select(Fare).where(Fare.fare_name == "Seat"))
        assert seat.berth == "seat"

        changed = offers[0].model_copy(update={"berth": "couchette"})
        later = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)
        upsert_offers(s, trip_id, None, [changed], source="oebbtickets.at", captured_at=later)
        s.commit()
        s.refresh(seat)
        assert seat.berth == "couchette"


def test_the_export_has_the_berth_and_the_import_keeps_it(sessions):
    with sessions() as s:
        trip = Trip(title="berth export")
        s.add(trip)
        s.commit()
        trip_id = trip.id
        upsert_offers(s, trip_id, None, nightjet_offers(), source="oebbtickets.at", captured_at=CAPTURED)
        s.commit()
        data = json.loads(json.dumps(trip_export(load_trip(s, trip_id)), default=str))

    by_name = {f["fare_name"]: f["berth"] for it in data["itineraries"] for f in it["fares"]}
    assert by_name == {"Seat": "seat", "Couchette": "couchette", "Sleeper": "sleeper"}

    with sessions() as s:
        r = import_trip(s, data)
        s.commit()
        imported = {f.fare_name: f.berth for f in s.scalars(select(Fare)) if f.itinerary.trip_id == r.trip_id}
    assert imported == {"Seat": "seat", "Couchette": "couchette", "Sleeper": "sleeper"}


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0040")
    engine = create_engine(empty_database_url)
    try:
        assert "berth" not in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.upgrade(cfg, "0041")
        assert "berth" in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.downgrade(cfg, "0040")
        assert "berth" not in {c["name"] for c in inspect(engine).get_columns("fares")}
    finally:
        engine.dispose()
