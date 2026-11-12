"""The days next to a trip that are cheaper than its cheapest price (#2524). A pure function: no database."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.nearby_days import nearby_days

TODAY = date(2026, 12, 1)


def eur_only(amount: Decimal, currency: str) -> Decimal | None:
    return amount if currency == "EUR" else None


def price(day: date, amount: str, source: str = "a", currency: str = "EUR"):
    return SimpleNamespace(day=day, price=Decimal(amount), source=source, currency=currency)


def test_one_cheaper_day_before_the_span():
    prices = [price(date(2026, 12, 19), "29"), price(date(2026, 12, 21), "59")]
    lines = nearby_days(prices, date(2026, 12, 20), date(2026, 12, 20), Decimal("49"), TODAY, eur_only)
    assert len(lines) == 1
    assert lines[0].day == date(2026, 12, 19)
    assert lines[0].less_eur == Decimal("20")
    assert lines[0].price_eur == Decimal("29")


def test_day_four_before_the_span_is_left_out():
    prices = [price(date(2026, 12, 16), "10")]
    assert nearby_days(prices, date(2026, 12, 20), date(2026, 12, 20), Decimal("49"), TODAY, eur_only) == []


def test_day_inside_the_span_is_left_out():
    prices = [price(date(2026, 12, 21), "10")]
    assert nearby_days(prices, date(2026, 12, 20), date(2026, 12, 22), Decimal("49"), TODAY, eur_only) == []


def test_day_before_today_is_left_out():
    prices = [price(date(2026, 11, 30), "10")]
    today = date(2026, 12, 1)
    assert nearby_days(prices, date(2026, 12, 2), date(2026, 12, 2), Decimal("49"), today, eur_only) == []


def test_two_sources_on_one_day_give_the_cheaper_one():
    prices = [price(date(2026, 12, 19), "35", source="a"), price(date(2026, 12, 19), "29", source="b")]
    lines = nearby_days(prices, date(2026, 12, 20), date(2026, 12, 20), Decimal("49"), TODAY, eur_only)
    assert len(lines) == 1
    assert lines[0].source == "b"
    assert lines[0].less_eur == Decimal("20")


def test_day_after_the_span_is_found():
    prices = [price(date(2026, 12, 23), "30")]
    lines = nearby_days(prices, date(2026, 12, 20), date(2026, 12, 21), Decimal("49"), TODAY, eur_only)
    assert [line.day for line in lines] == [date(2026, 12, 23)]


def test_day_not_cheaper_than_the_trip_is_left_out():
    prices = [price(date(2026, 12, 19), "49"), price(date(2026, 12, 21), "80")]
    assert nearby_days(prices, date(2026, 12, 20), date(2026, 12, 20), Decimal("49"), TODAY, eur_only) == []


def test_no_date_from_gives_empty_list():
    prices = [price(date(2026, 12, 19), "10")]
    assert nearby_days(prices, None, None, Decimal("49"), TODAY, eur_only) == []


def test_no_cheapest_gives_empty_list():
    prices = [price(date(2026, 12, 19), "10")]
    assert nearby_days(prices, date(2026, 12, 20), date(2026, 12, 20), None, TODAY, eur_only) == []


def test_foreign_currency_is_converted_and_lines_are_in_date_order():
    def conv(amount: Decimal, currency: str) -> Decimal | None:
        return (amount * Decimal("0.5")).quantize(Decimal("0.01")) if currency == "USD" else amount

    prices = [price(date(2026, 12, 21), "20"), price(date(2026, 12, 19), "40", currency="USD")]
    lines = nearby_days(prices, date(2026, 12, 20), date(2026, 12, 20), Decimal("49"), TODAY, conv)
    assert [line.day for line in lines] == [date(2026, 12, 19), date(2026, 12, 21)]
    assert lines[0].price_eur == Decimal("20.00")
    assert lines[0].currency == "USD"
    assert lines[0].less_eur == Decimal("29.00")
