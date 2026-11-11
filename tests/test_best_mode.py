"""The best row of each mode of a trip (trip:best-mode)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.best_mode import best_per_mode
from app.models import Fare, Itinerary, Leg
from app.ranking import Weights
from app.web.pages import row_cost

_NO_STALE = datetime.min.replace(tzinfo=UTC)
_WEIGHTS = Weights()  # no markup: the effective cost is the price


def _row(n, mode_summary, price, *, hours=2, dep_utc=datetime(2026, 12, 20, 6, 0, tzinfo=UTC), currency="EUR"):
    """A row of `trip_page()`: one leg of `mode_summary` from `dep_utc` for `hours`."""
    arr_utc = dep_utc + timedelta(hours=hours)
    it = Itinerary(fingerprint=f"fp{n}", depart_at=dep_utc, arrive_at=arr_utc, duration_min=hours * 60,
                   transfers=0, mode_summary=mode_summary)
    it.legs = [Leg(seq=0, mode=mode_summary.split("+")[0] if mode_summary else "", carrier="X", from_name="Berlin",
                   to_name="Paris", depart_at=dep_utc, depart_offset_min=0, arrive_at=arr_utc, arrive_offset_min=0)]
    fare = Fare(source="src", latest_price=Decimal(price), currency=currency, latest_captured_at=dep_utc)
    fare.itinerary = it
    _, cost = row_cost(it, [fare], [], _WEIGHTS, _NO_STALE)
    return it, fare, cost


def test_the_best_row_of_each_mode_with_its_difference_to_the_trip_best():
    # the flight adds 37.50 of its own parts: its price 102.50 gives an effective cost of 140.00
    flight = _row(1, "flight", "102.50", hours=0)
    train_a = _row(2, "train", "152.00", hours=0)
    train_b = _row(3, "train", "170.00", hours=0)
    result = best_per_mode([train_b, flight, train_a])
    assert [(mode, row[0].fingerprint, diff) for mode, row, diff in result] == [
        ("flight", "fp1", Decimal("0.00")),
        ("train", "fp2", Decimal("12.00")),
    ]


def test_a_row_with_two_modes_is_mixed():
    rows = [_row(1, "train+bus", "20.00"), _row(2, "train", "50.00")]
    result = best_per_mode(rows)
    assert [mode for mode, _row, _diff in result] == ["mixed", "train"]


def test_a_row_with_no_mode_summary_is_other():
    result = best_per_mode([_row(1, "", "20.00")])
    assert [mode for mode, _row, _diff in result] == ["other"]


def test_a_row_with_no_rate_does_not_count():
    no_rate = _row(1, "flight", "5.00", currency="CHF")
    rated = _row(2, "train", "50.00")
    result = best_per_mode([no_rate, rated])
    assert [(mode, row[0].fingerprint) for mode, row, _diff in result] == [("train", "fp2")]
    assert result[0][2] == Decimal("0.00")


def test_a_tie_in_a_mode_goes_to_the_earliest_departure():
    late = _row(1, "bus", "30.00", dep_utc=datetime(2026, 12, 20, 9, 0, tzinfo=UTC))
    early = _row(2, "bus", "30.00", dep_utc=datetime(2026, 12, 20, 7, 0, tzinfo=UTC))
    result = best_per_mode([late, early])
    assert [row[0].fingerprint for _mode, row, _diff in result] == ["fp2"]


def test_no_rows_give_an_empty_list():
    assert best_per_mode([]) == []
