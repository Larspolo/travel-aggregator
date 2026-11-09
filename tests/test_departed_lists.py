"""The trips list and the target marks skip the departed offers (#1393)."""

from datetime import datetime, timezone
from decimal import Decimal


import app.departed
from app.models import Itinerary, Trip
from app.target import at_target
from app.trips import list_trips
from tests.test_trip_hide import itinerary_at
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

NOW = datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc)


def _setup(trip, sessions, monkeypatch, early_price, late_price, target=None):  # noqa: F811
    """A departed offer at `early_price` (departed at 07:34 UTC) and a later one at `late_price`."""
    client, auth, tid = trip
    ingest(client, auth, tid, [offer(early_price, "ICE 1"), offer(late_price, "ICE 2")])
    early, late = itinerary_at(sessions, tid, early_price), itinerary_at(sessions, tid, late_price)
    with sessions() as s:
        s.get(Itinerary, early).depart_at = datetime(2026, 12, 1, 7, 34, tzinfo=timezone.utc)
        s.get(Itinerary, late).depart_at = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)
        s.get(Trip, tid).target_price = Decimal(target) if target else None
        s.commit()
    monkeypatch.setattr(app.departed, "clock", lambda: NOW)
    return client, tid, early


def test_the_best_offer_on_the_list_is_the_later_fare_not_the_departed_one(trip, sessions, monkeypatch):  # noqa: F811
    _setup(trip, sessions, monkeypatch, "39.00", "89.00")
    with sessions() as s:
        (row,) = list_trips(s)
    assert row.best_price == Decimal("89.00")


def test_the_count_skips_the_departed_offer(trip, sessions, monkeypatch):  # noqa: F811
    _setup(trip, sessions, monkeypatch, "39.00", "89.00")
    with sessions() as s:
        (row,) = list_trips(s)
    assert row.offer_count == 1


def test_a_departed_fare_at_the_target_is_not_at_target(trip, sessions, monkeypatch):  # noqa: F811
    _setup(trip, sessions, monkeypatch, "39.00", "89.00", target="80.00")
    with sessions() as s:
        assert at_target(s, s.get(Trip, trip[2])) == []
        (row,) = list_trips(s)
    assert row.at_target is False


def test_a_later_fare_at_the_target_still_is_at_target(trip, sessions, monkeypatch):  # noqa: F811
    _setup(trip, sessions, monkeypatch, "39.00", "75.00", target="80.00")
    with sessions() as s:
        found = at_target(s, s.get(Trip, trip[2]))
    assert [f.price for f in found] == [Decimal("75.00")]
