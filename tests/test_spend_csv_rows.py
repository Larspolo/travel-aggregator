"""The CSV rows of one year of "Travel per year" (#1729): plain objects, no database."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.spend import YEAR_CSV_COLUMNS, year_rows, year_summary

UTC = timezone.utc
USD_RATE = {"USD": Decimal("0.8571")}


def _leg(mode, depart, minutes, from_name="A", to_name="B", carrier=None, offset=0):
    return SimpleNamespace(mode=mode, carrier=carrier, from_name=from_name, to_name=to_name, depart_at=depart,
                           depart_offset_min=offset, arrive_at=depart + timedelta(minutes=minutes))


def _journey(legs, price=None, currency=None, cancelled_at=None, refund=None, delay=None, claim_paid_at=None,
             booked=True):
    depart = legs[0].depart_at
    minutes = sum(int((leg.arrive_at - leg.depart_at).total_seconds() // 60) for leg in legs)
    return SimpleNamespace(legs=legs, depart_at=depart, duration_min=minutes, booked=booked, booked_price=price,
                           booked_currency=currency, cancelled_at=cancelled_at, refund_price=refund,
                           delay_min=delay, claim_paid_at=claim_paid_at)


def _at(*args):
    return datetime(*args, tzinfo=UTC)


def _money(value):
    return Decimal(0) if value is None else value


def _journeys():
    booked = _journey([_leg("train", _at(2026, 1, 5, 9), 120, "Amsterdam", "Brussel", carrier="NS")],
                      Decimal("90.00"), "EUR")
    cancelled = _journey([_leg("flight", _at(2026, 3, 1, 8), 90, "Schiphol", "Rome", carrier="KL")],
                         Decimal("100.00"), "USD", cancelled_at=_at(2026, 2, 1), refund=Decimal("40.00"))
    claimed = _journey([_leg("train", _at(2026, 6, 1, 7), 200, "Paris", "Lyon", carrier="SNCF"),
                        _leg("train", _at(2026, 6, 1, 11), 30, "Lyon", "Nice", carrier="SNCF")],
                       Decimal("120.00"), "EUR", delay=130, claim_paid_at=_at(2026, 7, 1))
    no_rate = _journey([_leg("bus", _at(2026, 8, 1, 10), 60, "Bern", "Zurich", carrier="Bus")], Decimal("50.00"), "CHF")
    last_year = _journey([_leg("train", _at(2025, 12, 31, 20), 60, "Lille", "Paris", carrier="TGV")],
                         Decimal("80.00"), "EUR")
    return [claimed, last_year, no_rate, cancelled, booked]


def test_the_columns_are_in_the_order_of_the_spec():
    assert YEAR_CSV_COLUMNS == ["date", "route", "modes", "carriers", "status", "paid", "currency", "paid_eur",
                                "refund", "refund_eur", "claim_paid"]


def test_only_the_journeys_of_the_year_are_rows_in_the_order_of_departure():
    rows = year_rows(_journeys(), 2026, USD_RATE)
    assert [row[0] for row in rows] == ["2026-01-05", "2026-03-01", "2026-06-01", "2026-08-01"]
    assert all(row[0].startswith("2026") for row in rows)


def test_the_sum_of_paid_less_refund_equals_the_paid_total_of_the_year_summary():
    itineraries = _journeys()
    rows = year_rows(itineraries, 2026, USD_RATE)
    paid = sum(_money(row[7]) for row in rows)
    refund = sum(_money(row[9]) for row in rows)
    (year,) = [y for y in year_summary(itineraries, USD_RATE) if y.year == 2026]
    assert paid - refund == year.paid_eur == Decimal("261.43")


def test_a_cancelled_row_has_the_status_and_the_refund_in_its_currency():
    cancelled = year_rows(_journeys(), 2026, USD_RATE)[1]
    assert cancelled[1] == "Schiphol - Rome"
    assert cancelled[2] == "flight"
    assert cancelled[3] == "KL"
    assert cancelled[4] == "cancelled"
    assert cancelled[5:8] == [Decimal("100.00"), "USD", Decimal("85.71")]
    assert cancelled[8] == Decimal("40.00")
    assert cancelled[9] == Decimal("34.28")
    assert cancelled[10] is None


def test_a_claimed_row_has_the_claim_amount_and_joins_the_legs():
    claimed = year_rows(_journeys(), 2026, USD_RATE)[2]
    assert claimed[1] == "Paris - Nice"
    assert claimed[2] == "train"
    assert claimed[4] == "booked"
    assert claimed[8] is None and claimed[9] is None
    assert claimed[10] == Decimal("60.00")


def test_a_price_with_no_rate_has_none_in_the_eur_cells():
    no_rate = year_rows(_journeys(), 2026, USD_RATE)[3]
    assert no_rate[5:8] == [Decimal("50.00"), "CHF", None]
    assert no_rate[10] is None


def test_a_booked_row_without_a_claim_or_refund_has_none_in_those_cells():
    booked = year_rows(_journeys(), 2026, USD_RATE)[0]
    assert booked[0:5] == ["2026-01-05", "Amsterdam - Brussel", "train", "NS", "booked"]
    assert booked[5:8] == [Decimal("90.00"), "EUR", Decimal("90.00")]
    assert booked[8:11] == [None, None, None]


def test_a_journey_without_a_price_has_no_money_cells():
    unpriced = _journey([_leg("bus", _at(2026, 9, 1, 9), 30, "X", "Y")])
    row = year_rows([unpriced], 2026, USD_RATE)[0]
    assert row[4] == "booked"
    assert row[5:] == [None, "EUR", None, None, None, None]
