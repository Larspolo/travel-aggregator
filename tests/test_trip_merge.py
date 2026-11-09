"""Merge the data of one trip into another trip (#1261): app/trip_merge.py merge_trips()."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import Capture, DayPrice, Fare, FarePrice, Itinerary, Trip
from app.trip_merge import merge_trips


def _at(day, hour=10):
    return datetime(2026, 11, day, hour, tzinfo=UTC)


def _it(s, trip, fp, prices, source="stub", fare_name="Flex", **flags):
    it = Itinerary(trip_id=trip.id, fingerprint=fp, depart_at=_at(20, 8), arrive_at=_at(20, 11), duration_min=180,
                   first_seen_at=flags.pop("first", _at(1)), last_seen_at=_at(1), **flags)
    fare = Fare(source=source, fare_name=fare_name, latest_price=Decimal(prices[-1][0]), currency="EUR",
                latest_captured_at=_at(prices[-1][1]))
    fare.prices = [FarePrice(price=Decimal(p), currency="EUR", captured_at=_at(d)) for p, d in prices]
    it.fares.append(fare)
    s.add(it)
    return it


def _trips(s):
    a, b = Trip(title="A"), Trip(title="B")
    s.add_all([a, b])
    s.flush()
    for i in range(3):
        _it(s, a, f"a{i}", [("10.00", 1), ("12.00", 3)] if i == 0 else [("20.00", 1)],
            **({"pinned": True, "note": "source", "first": _at(1)} if i == 0 else {}))
    _it(s, b, "a0", [("11.00", 2)], note="target", first=_at(2))
    _it(s, b, "b1", [("30.00", 1)])
    s.add_all([Capture(trip_id=a.id, source="stub", captured_at=_at(3)),
               DayPrice(source="stub", trip_id=a.id, day=date(2026, 12, 1), price=Decimal("5"), currency="EUR",
                        captured_at=_at(3)),
               DayPrice(source="stub", trip_id=a.id, day=date(2026, 12, 2), price=Decimal("6"), currency="EUR",
                        captured_at=_at(1)),
               DayPrice(source="stub", trip_id=b.id, day=date(2026, 12, 2), price=Decimal("7"), currency="EUR",
                        captured_at=_at(2))])
    s.commit()
    return a.id, b.id


def test_the_merge_joins_one_journey_and_moves_the_rest(sessions):
    with sessions() as s:
        a, b = _trips(s)
        assert merge_trips(s, a, b) == {"moved": 2, "joined": 1, "captures": 1, "day_prices": 2}
    with sessions() as s:
        assert s.get(Trip, a) is None
        its = {it.fingerprint: it for it in s.scalars(select(Itinerary).where(Itinerary.trip_id == b))}
        assert sorted(its) == ["a0", "a1", "a2", "b1"]
        joined = its["a0"]
        assert len(joined.fares) == 1
        fare = joined.fares[0]
        assert sorted(p.price for p in fare.prices) == [Decimal("10.00"), Decimal("11.00"), Decimal("12.00")]
        assert fare.latest_price == Decimal("12.00") and fare.latest_captured_at == _at(3)
        assert joined.pinned and joined.note == "target" and joined.first_seen_at == _at(1)
        assert s.scalar(select(Capture.trip_id)) == b
        days = {d.day.day: d.price for d in s.scalars(select(DayPrice).where(DayPrice.trip_id == b))}
        assert days == {1: Decimal("5"), 2: Decimal("7")}


def test_a_note_of_the_source_goes_to_a_joined_itinerary_with_no_note(sessions):
    with sessions() as s:
        a, b = Trip(title="A"), Trip(title="B")
        s.add_all([a, b])
        s.flush()
        _it(s, a, "x", [("1", 1)], fare_name="Saver", note="mine", booked=True)
        _it(s, b, "x", [("2", 2)])
        s.commit()
        merge_trips(s, a.id, b.id)
        b_id = b.id
    with sessions() as s:
        it = s.scalars(select(Itinerary).where(Itinerary.trip_id == b_id)).one()
        assert it.note == "mine" and it.booked and len(it.fares) == 2


@pytest.mark.parametrize("case", ["same", "missing", "return_of", "split_of", "return_trip", "split_part"])
def test_a_wrong_merge_gives_value_error_and_changes_nothing(sessions, case):
    with sessions() as s:
        a, b = _trips(s)
        other = Trip(title="C")
        s.add(other)
        s.flush()
        src, tgt = a, b
        if case == "same":
            tgt = a
        elif case == "missing":
            tgt = 999999
        elif case == "return_of":
            s.get(Trip, a).return_of_id = other.id
        elif case == "split_of":
            s.get(Trip, a).split_of_id = other.id
        elif case == "return_trip":
            other.return_of_id = a
        else:
            other.split_of_id = a
        s.commit()
        with pytest.raises(ValueError):
            merge_trips(s, src, tgt)
    with sessions() as s:
        assert s.get(Trip, a) is not None
        assert s.scalar(select(func.count()).select_from(Itinerary).where(Itinerary.trip_id == a)) == 3
        assert s.scalar(select(func.count()).select_from(Itinerary).where(Itinerary.trip_id == b)) == 2
