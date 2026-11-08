"""The cheapest price of a trip per day for the price trend chart (#850)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.models import CurrencyRate, Fare, FarePrice, Itinerary, Trip
from app.trend import trip_trend


def _at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=UTC)


def _fare(s, trip, n, *, hidden=False):
    it = Itinerary(trip=trip, fingerprint=f"fp{n}", depart_at=_at(20), arrive_at=_at(20, 14),
                   duration_min=120, hidden=hidden)
    fare = Fare(itinerary=it, source="test", latest_price=Decimal("1"), currency="EUR",
                latest_captured_at=_at(1))
    s.add_all([it, fare])
    s.flush()
    return fare


def _price(s, fare, amount, currency, day, hour=12):
    s.add(FarePrice(fare=fare, price=Decimal(amount), currency=currency, captured_at=_at(day, hour)))


def _trip(s):
    trip = Trip(title="Trend")
    s.add(trip)
    s.flush()
    return trip


def test_two_fares_give_the_lowest_price_of_each_day(sessions):
    with sessions() as s:
        trip = _trip(s)
        a = _fare(s, trip, 1)
        b = _fare(s, trip, 2)
        _price(s, a, "90.00", "EUR", 1)
        _price(s, a, "99.00", "EUR", 3)
        _price(s, b, "85.00", "EUR", 2)
        s.commit()
        trip_id = trip.id
    with sessions() as s:
        assert trip_trend(s, trip_id) == [
            (date(2026, 11, 1), Decimal("90.00")),
            (date(2026, 11, 2), Decimal("85.00")),
            (date(2026, 11, 3), Decimal("85.00")),
        ]


def test_a_day_without_capture_keeps_the_value_of_the_day_before(sessions):
    with sessions() as s:
        trip = _trip(s)
        a = _fare(s, trip, 1)
        _price(s, a, "70.00", "EUR", 1)
        _price(s, a, "60.00", "EUR", 4)
        s.commit()
        trip_id = trip.id
    with sessions() as s:
        trend = trip_trend(s, trip_id)
    assert [d for d, _ in trend] == [date(2026, 11, n) for n in (1, 2, 3, 4)]
    assert [v for _, v in trend] == [Decimal("70.00")] * 3 + [Decimal("60.00")]


def test_a_hidden_itinerary_and_a_price_with_no_rate_do_not_count_and_chf_counts_in_eur(sessions):
    with sessions() as s:
        trip = _trip(s)
        s.add(CurrencyRate(code="CHF", eur_per_unit=Decimal("1.070000"), updated_at=_at(1)))  # no rate for XYZ
        hidden = _fare(s, trip, 1, hidden=True)
        no_rate = _fare(s, trip, 2)
        chf = _fare(s, trip, 3)
        _price(s, hidden, "10.00", "EUR", 1)
        _price(s, no_rate, "20.00", "XYZ", 1)
        _price(s, chf, "100.00", "CHF", 1)
        s.commit()
        trip_id = trip.id
    with sessions() as s:
        assert trip_trend(s, trip_id) == [(date(2026, 11, 1), Decimal("107.00"))]


def test_a_trip_with_no_prices_gives_an_empty_list(sessions):
    with sessions() as s:
        trip = _trip(s)
        _fare(s, trip, 1)
        s.commit()
        trip_id = trip.id
    with sessions() as s:
        assert trip_trend(s, trip_id) == []
