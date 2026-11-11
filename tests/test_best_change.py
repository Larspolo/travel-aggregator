"""The days on which the best itinerary of a trip changed (#2165)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import Fare, FarePrice, Itinerary, Trip
from app.ranking import Weights
from app.trend_score import best_changes


def _at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=UTC)


def _fare(s, trip, n, hours, depart=6):
    it = Itinerary(trip=trip, fingerprint=f"fp{n}", depart_at=_at(20, depart), arrive_at=_at(20, depart + hours),
                   duration_min=hours * 60)
    fare = Fare(itinerary=it, source="test", latest_price=Decimal("1"), currency="EUR", latest_captured_at=_at(1))
    s.add_all([it, fare])
    s.flush()
    return fare


def _price(s, fare, amount, day):
    s.add(FarePrice(fare=fare, price=Decimal(amount), currency="EUR", captured_at=_at(day)))


def _changes(s, trip_id, hour="10"):
    return best_changes(s, s.get(Trip, trip_id), Weights(hour_markup=Decimal(hour)), [])


def _bus_and_ice(sessions):
    with sessions() as s:
        trip = Trip(title="Change")
        s.add(trip)
        s.flush()
        bus, ice = _fare(s, trip, 1, 8), _fare(s, trip, 2, 4)
        _price(s, bus, "30.00", 3)  # 30 + 80 = 110
        _price(s, ice, "90.00", 3)  # 90 + 40 = 130
        _price(s, bus, "35.00", 5)  # 115
        _price(s, ice, "60.00", 5)  # 100
        s.commit()
        return trip.id, bus.itinerary_id, ice.itinerary_id


def test_a_price_drop_makes_the_ice_best(sessions):
    trip_id, bus, ice = _bus_and_ice(sessions)
    with sessions() as s:
        [(day, old, old_cost, new, new_cost)] = _changes(s, trip_id)
    assert (day, old.id, old_cost, new.id, new_cost) == (date(2026, 11, 5), bus, Decimal("115.00"), ice,
                                                         Decimal("100.00"))


def test_a_higher_hour_value_gives_no_entry_for_the_first_day(sessions):
    trip_id, _, _ = _bus_and_ice(sessions)
    with sessions() as s:
        assert _changes(s, trip_id, "20") == []  # the ICE is best from 3 Nov


def test_no_change_and_seven_changes(sessions):
    with sessions() as s:
        trip = Trip(title="Seven")
        s.add(trip)
        s.flush()
        a, b, same = _fare(s, trip, 1, 1), _fare(s, trip, 2, 1, depart=7), _fare(s, trip, 3, 1, depart=5)
        _price(s, a, "10.00", 1)
        s.commit()
        trip_id = trip.id
        for day in range(2, 9):
            _price(s, a if day % 2 else b, "5.00", day)
            _price(s, b if day % 2 else a, "10.00", day)
        s.commit()
        with sessions() as s2:
            changes = _changes(s2, trip_id)
        assert [c[0] for c in changes] == [date(2026, 11, d) for d in (8, 7, 6, 5, 4)]
        assert changes[0][3].id == b.itinerary_id
        _price(s, same, "15.00", 9)  # the same cost as the best: no change
        s.commit()
        with sessions() as s2:
            assert _changes(s2, trip_id)[0][0] == date(2026, 11, 8)


def test_a_trip_that_never_changes(sessions):
    with sessions() as s:
        trip = Trip(title="One")
        s.add(trip)
        s.flush()
        a, b = _fare(s, trip, 1, 1), _fare(s, trip, 2, 1, depart=7)
        _price(s, a, "10.00", 1)
        _price(s, b, "10.00", 1)  # a tie: the earliest departure
        _price(s, a, "12.00", 3)
        _price(s, b, "12.00", 3)
        s.commit()
        trip_id = trip.id
    with sessions() as s:
        assert _changes(s, trip_id) == []
