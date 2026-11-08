"""The trips list shows the best offer by its EUR value, and the journey total adds two EUR values (#386)."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import CurrencyRate, Fare, Itinerary, Trip
from app.trips import TripRow, _journey_total, list_trips

T = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def _offer(trip: Trip, fp: str, price: str, currency: str) -> Itinerary:
    it = Itinerary(trip=trip, fingerprint=fp, depart_at=T, arrive_at=T, duration_min=60)
    it.fares.append(Fare(source="x", latest_price=Decimal(price), currency=currency, latest_captured_at=T))
    return it


def _rate(code: str, eur: str) -> CurrencyRate:
    return CurrencyRate(code=code, eur_per_unit=Decimal(eur), updated_at=T)


def _row(**kw) -> TripRow:
    base = dict(id=1, title="t", origin_text=None, destination_text=None, date_from=None, date_to=None,
                status="active", offer_count=1, best_price=None, best_currency=None)
    return TripRow(**{**base, **kw})


def test_the_best_offer_is_the_lowest_eur_value(sessions):
    with sessions() as s:
        trip = Trip(title="Prague", origin_text="A", destination_text="B")
        s.add_all([trip, _rate("CZK", "0.04"), _offer(trip, "eur", "40.00", "EUR"), _offer(trip, "czk", "900", "CZK")])
        s.commit()
    with sessions() as s:
        (row,) = list_trips(s)
    assert row.best_price == Decimal("36.00")
    assert row.best_currency == "EUR"
    assert row.no_rate is False


def test_a_trip_with_only_fares_without_a_rate_shows_its_price_and_no_rate(sessions):
    with sessions() as s:
        trip = Trip(title="Stockholm", origin_text="A", destination_text="B")
        s.add_all([trip, _offer(trip, "sek", "700", "SEK")])
        s.commit()
    with sessions() as s:
        (row,) = list_trips(s)
    assert row.best_price == Decimal("700.00")
    assert row.best_currency == "SEK"
    assert row.no_rate is True


def test_a_fare_without_a_rate_does_not_count_when_another_has_a_rate(sessions):
    with sessions() as s:
        trip = Trip(title="Oslo", origin_text="A", destination_text="B")
        s.add_all([trip, _rate("CHF", "1.07"), _offer(trip, "sek", "10", "SEK"), _offer(trip, "chf", "120", "CHF")])
        s.commit()
    with sessions() as s:
        (row,) = list_trips(s)
    assert row.best_price == Decimal("128.40")
    assert row.best_currency == "EUR"
    assert row.no_rate is False


def test_the_journey_total_of_a_chf_outbound_and_a_eur_return_is_in_eur():
    out = _row(id=1, best_price=Decimal("128.40"), best_currency="EUR")
    ret = _row(id=2, best_price=Decimal("30.00"), best_currency="EUR")
    assert _journey_total(out, ret) == "EUR 158.40"


def test_the_journey_total_is_no_total_for_a_fare_without_a_rate():
    out = _row(id=1, best_price=Decimal("128.40"), best_currency="EUR")
    ret = _row(id=2, best_price=Decimal("50"), best_currency="SEK", no_rate=True)
    assert _journey_total(out, ret) == "no total"


def test_the_list_is_one_statement_with_the_rates(sessions):
    from sqlalchemy import event

    engine = sessions.kw["bind"]
    with sessions() as s:
        s.add(_rate("CZK", "0.04"))
        s.commit()
    statements = []
    event.listen(engine, "before_cursor_execute", lambda *a: statements.append(a[2]))
    with Session(engine) as s:
        list_trips(s)
    assert len(statements) == 1
