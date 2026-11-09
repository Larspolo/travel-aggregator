"""A gone fare does not count for the best offer of the trips list or for the target (#1387)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Capture, Fare, FarePrice, Itinerary, Trip
from app.target import at_target
from app.trips import list_trips

DAY = datetime(2026, 12, 1, tzinfo=timezone.utc)
C1 = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
C2 = C1 + timedelta(hours=1)


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


def _fare(s, trip, hour, price, seen=C1):
    it = Itinerary(trip=trip, fingerprint=f"gl-{trip.title}-{hour}", depart_at=DAY + timedelta(hours=hour),
                   arrive_at=DAY + timedelta(hours=hour + 2), duration_min=120)
    f = Fare(itinerary=it, source="bahn.de", latest_price=Decimal(price), currency="EUR", latest_captured_at=seen)
    s.add(f)
    return f


def _capture(s, trip, at, fares):
    s.flush()
    c = Capture(trip_id=trip.id, source="bahn.de", captured_at=at)
    s.add(c)
    s.flush()
    for f in fares:
        f.prices.append(FarePrice(price=f.latest_price, currency="EUR", captured_at=at, capture_id=c.id))
        f.latest_captured_at = max(f.latest_captured_at, at)


def _trip(s, title, target=None):
    trip = Trip(title=title, target_price=target)
    gone = _fare(s, trip, 9, "39.00")
    _capture(s, trip, C1, [gone])
    _capture(s, trip, C2, [_fare(s, trip, 8, "89.00", seen=C2), _fare(s, trip, 12, "95.00", seen=C2)])
    return trip


def test_the_list_skips_a_gone_fare(engine):
    with Session(engine) as s:
        trip = _trip(s, "Gone list")
        s.commit()
        row = next(r for r in list_trips(s) if r.id == trip.id)
        assert row.best_price == Decimal("89.00")
        assert row.offer_count == 3


def test_a_gone_fare_is_not_at_target(engine):
    with Session(engine) as s:
        trip = _trip(s, "Gone target", target=Decimal("50.00"))
        s.commit()
        assert at_target(s, trip) == []
        row = next(r for r in list_trips(s) if r.id == trip.id)
        assert not row.at_target
