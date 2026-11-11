"""The bicycle transport of a fare (#2457): the ingest stores it, a newer capture updates it, an older capture does
not; the schema keeps only a known value; the migration upgrades and downgrades to a named revision."""

import copy
from datetime import UTC, datetime

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Fare, Trip
from app.schemas import IngestIn
from tests.test_ingest_api import BODY

T1 = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
T2 = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)


def offer(**update):
    b = copy.deepcopy(BODY)
    b["trip_id"] = 1
    o = b["offers"][0]
    o["price_amount"], o["fare_name"] = "89.90", "Sparpreis"
    o.update(update)
    return IngestIn(**b).offers[0]


def store(sessions, offers, at):
    with sessions() as s:
        trip = Trip(title="bike")
        s.add(trip)
        s.commit()
        upsert_offers(s, trip.id, None, offers, source="bahn.de", captured_at=at)
        s.commit()
        return trip.id


def bike_of(sessions, trip_id):
    with sessions() as s:
        return s.scalar(select(Fare.bike).where(
            Fare.fare_name == "Sparpreis", Fare.itinerary.has(trip_id=trip_id)))


def test_the_offer_with_a_bike_reservation_stores_reservation(sessions):
    trip_id = store(sessions, [offer(bike="reservation")], T1)
    assert bike_of(sessions, trip_id) == "reservation"


def test_a_newer_capture_with_no_bike_changes_it_to_no(sessions):
    trip_id = store(sessions, [offer(bike="reservation")], T1)
    with sessions() as s:
        upsert_offers(s, trip_id, None, [offer(bike="no", price_amount="79.90")], source="bahn.de", captured_at=T2)
        s.commit()
    assert bike_of(sessions, trip_id) == "no"


def test_an_older_capture_does_not_change_the_bike(sessions):
    trip_id = store(sessions, [offer(bike="no", price_amount="79.90")], T2)
    with sessions() as s:
        upsert_offers(s, trip_id, None, [offer(bike="allowed")], source="bahn.de", captured_at=T1)
        s.commit()
    assert bike_of(sessions, trip_id) == "no"


def test_an_offer_without_bike_stores_none(sessions):
    trip_id = store(sessions, [offer()], T1)
    assert bike_of(sessions, trip_id) is None


def test_the_schema_rejects_an_unknown_bike_value():
    b = copy.deepcopy(BODY)
    b["trip_id"] = 1
    b["offers"][0]["bike"] = "maybe"
    body = IngestIn(**b)
    assert body.offers == []
    assert [e["index"] for e in body.offer_errors] == [0]


def test_the_migration_upgrades_and_downgrades_to_0062(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0062")
    engine = create_engine(empty_database_url)
    try:
        assert "bike" not in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.upgrade(cfg, "0063")
        assert "bike" in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.downgrade(cfg, "0062")
        assert "bike" not in {c["name"] for c in inspect(engine).get_columns("fares")}
    finally:
        engine.dispose()
