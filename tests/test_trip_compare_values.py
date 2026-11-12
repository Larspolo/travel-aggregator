"""The values of a trip on the compare-trips page: best, cheapest, fastest, count and newest capture (#2554)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.models import Capture, CurrencyRate, Fare, Itinerary, Leg, Trip
from app.trip_compare import trip_values

NOW = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
DEP = datetime(2026, 12, 20, 6, 0, tzinfo=UTC)


def _trip(s):
    trip = Trip(title="Berlin", date_from=date(2026, 12, 20), date_to=date(2026, 12, 25))
    s.add(trip)
    s.flush()
    return trip


def _offer(s, trip, n, price, *, hours=2, dep=DEP, hidden=False, booked=False, currency="EUR"):
    arr = dep + timedelta(hours=hours)
    it = Itinerary(trip_id=trip.id, fingerprint=f"fp{n}", mode_summary="flight", depart_at=dep, arrive_at=arr,
                   duration_min=hours * 60, transfers=0, hidden=hidden, booked=booked)
    it.legs = [Leg(seq=0, mode="flight", carrier="X", service_no=f"X{n}", from_name="Berlin", to_name="Paris",
                   depart_at=dep, depart_offset_min=0, arrive_at=arr, arrive_offset_min=0)]
    it.fares = [Fare(source="src", latest_price=Decimal(price), currency=currency, latest_captured_at=dep)]
    s.add(it)
    s.flush()
    return it


def test_a_trip_with_three_offers_gives_its_best_cheapest_fastest_count_and_newest_capture(sessions):
    with sessions() as s:
        trip = _trip(s)
        slow_cheap = _offer(s, trip, 1, "80.00", hours=5)
        mid = _offer(s, trip, 2, "120.00", hours=3)
        quick = _offer(s, trip, 3, "150.00", hours=1)
        s.add(Capture(trip_id=trip.id, source="src", captured_at=datetime(2026, 12, 1, 9, 0, tzinfo=UTC)))
        s.add(Capture(trip_id=trip.id, source="src", captured_at=datetime(2026, 12, 1, 10, 30, tzinfo=UTC)))
        s.commit()

        values = trip_values(s, s.get(Trip, trip.id), NOW)

        assert values.date_from == date(2026, 12, 20) and values.date_to == date(2026, 12, 25)
        assert values.best is not None
        assert values.best[0].id == slow_cheap.id  # the lowest effective cost: the price only, no weights set
        assert values.best[1].latest_price == Decimal("80.00")
        assert values.cheapest[0].id == slow_cheap.id and values.cheapest[1].latest_price == Decimal("80.00")
        assert values.fastest[0].id == quick.id
        assert values.count == 3
        assert values.newest_capture == datetime(2026, 12, 1, 10, 30, tzinfo=UTC)
        assert mid.id != values.fastest[0].id


def test_the_cheapest_offer_compares_the_price_in_eur(sessions):
    with sessions() as s:
        trip = _trip(s)
        _offer(s, trip, 1, "100.00", currency="EUR")
        usd = _offer(s, trip, 2, "90.00", currency="USD")
        s.add(CurrencyRate(code="USD", eur_per_unit=Decimal("0.5"), updated_at=NOW))  # 90 USD = 45 EUR
        s.commit()

        values = trip_values(s, s.get(Trip, trip.id), NOW)

        assert values.cheapest[0].id == usd.id
        assert values.cheapest[1].latest_price == Decimal("90.00")


def test_a_trip_with_no_offers_gives_no_best_offer_and_the_count_zero(sessions):
    with sessions() as s:
        trip = _trip(s)
        s.commit()

        values = trip_values(s, s.get(Trip, trip.id), NOW)

        assert values.best is None
        assert values.cheapest is None
        assert values.fastest is None
        assert values.count == 0
        assert values.newest_capture is None


def test_a_hidden_or_departed_offer_does_not_count(sessions):
    with sessions() as s:
        trip = _trip(s)
        _offer(s, trip, 1, "100.00")
        _offer(s, trip, 2, "10.00", hidden=True)
        _offer(s, trip, 3, "10.00", dep=datetime(2026, 11, 30, 6, 0, tzinfo=UTC))  # departed, not booked
        s.commit()

        values = trip_values(s, s.get(Trip, trip.id), NOW)

        assert values.count == 1
        assert values.best[1].latest_price == Decimal("100.00")
        assert values.cheapest[1].latest_price == Decimal("100.00")
        assert values.fastest[1].latest_price == Decimal("100.00")
