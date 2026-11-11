"""The seats left of a fare (#1823): the ingest stores the count, a newer capture updates it, an older capture does
not; the parser helper keeps only a valid count; the migration upgrades and downgrades to a named revision."""

import copy
from datetime import UTC, datetime

from sqlalchemy import inspect, select

from app.ingest import upsert_offers
from app.models import Fare, Trip
from app.parsers import seats
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
        trip = Trip(title="seats")
        s.add(trip)
        s.commit()
        upsert_offers(s, trip.id, None, offers, source="bahn.de", captured_at=at)
        s.commit()
        return trip.id


def seats_of(sessions, trip_id):
    with sessions() as s:
        return s.scalar(select(Fare.seats_left).where(
            Fare.fare_name == "Sparpreis", Fare.itinerary.has(trip_id=trip_id)))


def test_the_offer_with_two_seats_left_stores_two(sessions):
    trip_id = store(sessions, [offer(seats_left=2)], T1)
    assert seats_of(sessions, trip_id) == 2


def test_a_newer_capture_with_nine_seats_updates_the_count(sessions):
    trip_id = store(sessions, [offer(seats_left=2)], T1)
    with sessions() as s:
        upsert_offers(s, trip_id, None, [offer(seats_left=9, price_amount="79.90")], source="bahn.de", captured_at=T2)
        s.commit()
    assert seats_of(sessions, trip_id) == 9


def test_a_newer_capture_with_no_count_stores_none(sessions):
    trip_id = store(sessions, [offer(seats_left=2)], T1)
    with sessions() as s:
        upsert_offers(s, trip_id, None, [offer(seats_left=None)], source="bahn.de", captured_at=T2)
        s.commit()
    assert seats_of(sessions, trip_id) is None


def test_an_older_capture_does_not_change_the_count(sessions):
    trip_id = store(sessions, [offer(seats_left=9, price_amount="79.90")], T2)
    with sessions() as s:
        upsert_offers(s, trip_id, None, [offer(seats_left=30)], source="bahn.de", captured_at=T1)
        s.commit()
    assert seats_of(sessions, trip_id) == 9


def test_the_parser_helper_keeps_only_a_valid_count():
    assert seats(2) == 2
    assert seats(0) == 0
    for bad in (True, "2", -1, 10000, None, 2.0):
        assert seats(bad) is None


def test_the_migration_upgrades_and_downgrades_to_0042(empty_database_url):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0042")
    engine = create_engine(empty_database_url)
    try:
        assert "seats_left" not in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.upgrade(cfg, "0043")
        assert "seats_left" in {c["name"] for c in inspect(engine).get_columns("fares")}
        command.downgrade(cfg, "0042")
        assert "seats_left" not in {c["name"] for c in inspect(engine).get_columns("fares")}
    finally:
        engine.dispose()
