"""upsert_offers (#31): one itinerary per journey, a price row only for a new fare or a changed price."""

import copy
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.ingest import upsert_offers
from app.models import Fare, FarePrice, Itinerary, Trip
from app.schemas import IngestIn
from tests.test_ingest_api import BODY

T1 = datetime(2026, 11, 3, 19, 41, tzinfo=UTC)
T2 = datetime(2026, 11, 4, 8, 0, tzinfo=UTC)


@pytest.fixture
def trip_id(sessions):
    with sessions() as s:
        trip = Trip(title="t")
        s.add(trip)
        s.commit()
        return trip.id


def offer(price="89.90", fare="Sparpreis"):
    b = copy.deepcopy(BODY)
    b["trip_id"] = 1
    o = b["offers"][0]
    o["price_amount"], o["fare_name"] = price, fare
    return IngestIn(**b).offers[0]


def run(sessions, trip_id, offers, at=T1):
    with sessions() as s:
        return upsert_offers(s, trip_id, None, offers, source="bahn.de", captured_at=at)


def count(sessions, model):
    with sessions() as s:
        return s.scalar(select(func.count()).select_from(model))


def test_a_new_price_adds_a_row_and_an_equal_price_does_not(sessions, trip_id):
    assert run(sessions, trip_id, [offer()]) == {"created": 1, "updated": 0, "unchanged": 0}
    assert run(sessions, trip_id, [offer("79.90")], T2) == {"created": 0, "updated": 1, "unchanged": 0}
    assert run(sessions, trip_id, [offer("79.90")], T2) == {"created": 0, "updated": 0, "unchanged": 1}
    assert count(sessions, Itinerary) == 1 and count(sessions, FarePrice) == 2
    with sessions() as s:
        assert s.scalar(select(Fare)).latest_price == Decimal("79.90")


def test_a_second_fare_adds_a_fare_not_an_itinerary(sessions, trip_id):
    run(sessions, trip_id, [offer()])
    assert run(sessions, trip_id, [offer("120.00", "Flexpreis")]) == {"created": 0, "updated": 1, "unchanged": 0}
    assert count(sessions, Itinerary) == 1 and count(sessions, Fare) == 2 and count(sessions, FarePrice) == 2


def test_a_batch_with_the_same_journey_twice_counts_both(sessions, trip_id):
    assert run(sessions, trip_id, [offer(), offer()]) == {"created": 1, "updated": 0, "unchanged": 1}
