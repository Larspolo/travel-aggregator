"""The mark "booked" keeps the paid fare, price and time (#1146, epic #1145)."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import create_engine, inspect, select

from app import ingest as ingest_mod
from app import tokens
from app.models import Fare, Itinerary, Trip
from tests.test_capture_move import _capture, _offer, _trip, stub  # noqa: F401
from tests.test_trip_booked import _alembic, _itinerary_id, booked_url, csrf
from tests.test_trip_booked import trip as booked_trip  # noqa: F401
from tests.test_trip_page import ingest, offer


def _paid(sessions, it_id):
    with sessions() as s:
        it = s.get(Itinerary, it_id)
        return it.booked_fare_id, it.booked_price, it.booked_currency, it.booked_at


def test_book_stores_the_main_fare_and_unbook_clears_it(sessions, booked_trip):  # noqa: F811
    client, trip_id = booked_trip
    with sessions() as s:
        token = tokens.create(s, "cheap")
    ingest(client, {"Authorization": f"Bearer {token}"}, trip_id, [offer("59.80", fare="Super Sparpreis")])
    it_id = _itinerary_id(sessions, trip_id)
    client.post(booked_url(trip_id, it_id), data={"csrf_token": csrf(client, trip_id)})
    fare_id, price, currency, at = _paid(sessions, it_id)
    with sessions() as s:
        assert s.get(Fare, fare_id).latest_price == Decimal("59.80")
    assert (price, currency) == (Decimal("59.80"), "EUR")
    assert at.utcoffset() == timedelta(0)
    client.post(booked_url(trip_id, it_id), data={"csrf_token": csrf(client, trip_id)})
    assert _paid(sessions, it_id) == (None, None, None, None)


def test_a_moved_capture_keeps_the_paid_values(sessions, stub):  # noqa: F811
    with sessions() as s:
        a, b = _trip(s, "A"), _trip(s, "B")
        cap = _capture(s, a, [_offer(8, "10.50")])
        it = s.scalars(select(Itinerary).where(Itinerary.trip_id == a)).one()
        fare = it.fares[0]
        it.booked, it.booked_fare_id, it.booked_price, it.booked_currency = True, fare.id, Decimal("10.50"), "EUR"
        it.booked_at = fare.latest_captured_at
        s.commit()
        ingest_mod.move_capture(s, cap, b)
    with sessions() as s:
        moved = s.scalars(select(Itinerary).where(Itinerary.trip_id == b)).one()
        assert (moved.booked, moved.booked_price, moved.booked_currency) == (True, Decimal("10.50"), "EUR")
        assert moved.booked_at is not None
        assert s.get(Trip, a) is not None


def test_the_migration_upgrades_and_downgrades(empty_database_url):
    from alembic import command

    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "0024")
    engine = create_engine(empty_database_url)
    cols = {"booked_fare_id", "booked_price", "booked_currency", "booked_at"}
    try:
        assert cols <= {c["name"] for c in inspect(engine).get_columns("itineraries")}
        command.downgrade(cfg, "0023")
        assert not cols & {c["name"] for c in inspect(engine).get_columns("itineraries")}
    finally:
        engine.dispose()
