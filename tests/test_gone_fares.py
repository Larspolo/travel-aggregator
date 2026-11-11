"""Fares that a newer capture of the same source did not show (#1385)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.gone import GoneMark, gone_fares
from app.models import Capture, Fare, FarePrice, Itinerary, Trip

DAY = datetime(2026, 12, 1, tzinfo=timezone.utc)
C1 = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
C2 = C1 + timedelta(hours=1)
_N = count()


@pytest.fixture
def engine(sessions):
    return sessions.kw["bind"]


def _fare(s, trip, hour, source="bahn.de", seen=C1):
    it = Itinerary(trip=trip, fingerprint=f"{source}-{hour}-{next(_N)}", depart_at=DAY + timedelta(hours=hour),
                   arrive_at=DAY + timedelta(hours=hour + 2), duration_min=120)
    f = Fare(itinerary=it, source=source, latest_price=Decimal("20.00"), currency="EUR", latest_captured_at=seen)
    s.add(f)
    return f


def _capture(s, trip, at, fares, source="bahn.de", mismatch=None):
    s.flush()
    c = Capture(trip_id=trip.id, source=source, captured_at=at, mismatch=mismatch)
    departs = [f.itinerary.depart_at for f in fares]  # the span of the offers of the capture (#1404)
    c.depart_from, c.depart_to = (min(departs), max(departs)) if departs else (None, None)
    s.add(c)
    s.flush()
    for f in fares:
        f.prices.append(FarePrice(price=f.latest_price, currency="EUR", captured_at=at, capture_id=c.id))
        f.latest_captured_at = max(f.latest_captured_at, at)
    return c


def test_gone_fares(engine):
    with Session(engine) as s:
        trip = Trip(title="Berlin")
        early, gone, kept, late = (_fare(s, trip, h) for h in (6, 9, 12, 20))
        other = _fare(s, trip, 10, source="flixbus")
        _capture(s, trip, C1, [early, gone, kept, late])
        _capture(s, trip, C1, [other], source="flixbus")
        _capture(s, trip, C2, [_fare(s, trip, 8, seen=C2), kept])  # span 08:00 to 12:00
        s.commit()
        trip_id, gone_id = trip.id, gone.id
        statements = []
        event.listen(engine, "before_cursor_execute", lambda *a: statements.append(a[2]))
        marks = gone_fares(s, [trip_id])
        assert len(statements) <= 2
        assert marks == {gone_id: GoneMark(source="bahn.de", captured_at=C2)}


def test_no_mark_for_mismatch_or_empty_capture(engine):
    with Session(engine) as s:
        trip = Trip(title="Berlin")
        a, b = _fare(s, trip, 9), _fare(s, trip, 10)
        _capture(s, trip, C1, [a, b])
        _capture(s, trip, C2, [_fare(s, trip, 8, seen=C2), _fare(s, trip, 12, seen=C2)], mismatch="date")
        _capture(s, trip, C2 + timedelta(hours=1), [])
        s.commit()
        assert gone_fares(s, [trip.id]) == {}
        assert gone_fares(s, []) == {}


def test_mark_bound_inclusive_and_later_reprice(engine):
    with Session(engine) as s:
        trip = Trip(title="Berlin")
        edge, back = _fare(s, trip, 11), _fare(s, trip, 10)
        _capture(s, trip, C1, [edge, back])
        _capture(s, trip, C2, [_fare(s, trip, 11, seen=C2),
                                _fare(s, trip, 7, seen=C2)])  # span 07:00 to 11:00
        _capture(s, trip, C2 + timedelta(hours=1), [back])  # priced again later
        s.commit()
        assert set(gone_fares(s, [trip.id])) == {edge.id}
