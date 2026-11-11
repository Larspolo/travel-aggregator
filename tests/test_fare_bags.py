"""The checked bags of a fare at ingest (#1525)."""
import copy
from decimal import Decimal

from alembic import command
from sqlalchemy import create_engine, inspect

from app.models import Fare
from tests.test_ingest_api import BODY
from tests.test_trip_booked import _alembic
from tests.test_trip_page import offer, trip  # noqa: F401  (trip is a fixture)

COLS = {"checked_bags_included", "checked_bag_price"}


def _ingest(client, auth, trip_id, o):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, offers=[o])
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200
    return r.json()


def _bags(sessions):
    with sessions() as s:
        return [(f.checked_bags_included, f.checked_bag_price) for f in s.query(Fare).all()]


def test_the_fare_stores_and_updates_its_bags(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _ingest(client, auth, tid, {**offer("39.00"), "checked_bags_included": 1, "checked_bag_price": "25.06"})
    assert _bags(sessions) == [(1, Decimal("25.06"))]
    _ingest(client, auth, tid, {**offer("49.00"), "checked_bags_included": 0, "checked_bag_price": "30.00"})
    assert _bags(sessions) == [(0, Decimal("30.00"))]
    _ingest(client, auth, tid, {**offer("49.00"), "checked_bags_included": 2, "checked_bag_price": "31.00"})
    assert _bags(sessions) == [(2, Decimal("31.00"))]  # the same price also updates the bags


def test_an_offer_with_no_bags_stores_none(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    _ingest(client, auth, tid, offer("39.00"))
    assert _bags(sessions) == [(None, None)]


def test_ten_bags_is_a_rejected_offer(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    counts = _ingest(client, auth, tid, {**offer("39.00"), "checked_bags_included": 10})
    assert counts["rejected"] == 1 and counts["created"] == 0


def test_migration_0031_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        def cols():
            return {c["name"] for c in inspect(engine).get_columns("fares")}
        assert COLS <= cols()
        command.downgrade(cfg, "0030")
        assert not COLS & cols()
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
