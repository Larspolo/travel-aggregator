"""The best effective cost of a trip per day (#2140)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import Fare, FarePrice, Itinerary, Trip
from app.ranking import Weights
from app.trend import trip_trend
from app.trend_score import trip_score_trend


def _at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=UTC)


def _fare(s, trip, n, hours, *, hidden=False):
    it = Itinerary(trip=trip, fingerprint=f"fp{n}", depart_at=_at(20, 6), arrive_at=_at(20, 6 + hours),
                   duration_min=hours * 60, hidden=hidden)
    fare = Fare(itinerary=it, source="test", latest_price=Decimal("1"), currency="EUR",
                latest_captured_at=_at(1))
    s.add_all([it, fare])
    s.flush()
    return fare


def _price(s, fare, amount, day, hour=12):
    s.add(FarePrice(fare=fare, price=Decimal(amount), currency="EUR", captured_at=_at(day, hour)))


def _trip(s):
    trip = Trip(title="Score")
    s.add(trip)
    s.flush()
    return trip


def _score(s, trip_id, hour="15"):
    return trip_score_trend(s, s.get(Trip, trip_id), Weights(hour_markup=Decimal(hour)), [])


def _setup(sessions):
    with sessions() as s:
        trip = _trip(s)
        train = _fare(s, trip, 1, 4)
        bus = _fare(s, trip, 2, 9)
        hidden = _fare(s, trip, 3, 1, hidden=True)
        _price(s, bus, "40.00", 1)
        _price(s, hidden, "1.00", 1)
        _price(s, train, "90.00", 2)
        _price(s, bus, "20.00", 4, 9)
        _price(s, train, "130.00", 4, 10)
        s.commit()
        return trip.id


def test_the_best_cost_of_each_day(sessions):
    trip_id = _setup(sessions)
    with sessions() as s:
        assert _score(s, trip_id) == [
            (date(2026, 11, 1), Decimal("175.00")),  # only the bus: 40 + 9 * 15
            (date(2026, 11, 2), Decimal("150.00")),  # the train has its first price: 90 + 4 * 15
            (date(2026, 11, 3), Decimal("150.00")),  # no capture: the value of the day before
            (date(2026, 11, 4), Decimal("155.00")),  # bus 20 + 135; train 130 + 60
        ]


def test_a_higher_hour_value_gives_higher_values_and_the_price_trend_is_the_same(sessions):
    trip_id = _setup(sessions)
    with sessions() as s:
        low, high = _score(s, trip_id, "15"), _score(s, trip_id, "20")
        trend = trip_trend(s, trip_id)
    assert all(h > lo for (_, lo), (_, h) in zip(low, high, strict=True))
    assert [v for _, v in trend] == [Decimal("40.00"), Decimal("40.00"), Decimal("40.00"), Decimal("20.00")]


def test_a_trip_with_no_price_row_gives_nothing(sessions):
    with sessions() as s:
        trip = _trip(s)
        _fare(s, trip, 1, 4)
        s.commit()
        trip_id = trip.id
    with sessions() as s:
        assert _score(s, trip_id) == []
