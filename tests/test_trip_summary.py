"""The text summary of the best rows of a trip (#2161)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models import Fare, Itinerary, Leg
from app.ranking import Weights
from app.trip_summary import trip_summary
from app.web.pages import row_cost

_NO_STALE = datetime.min.replace(tzinfo=UTC)
_WEIGHTS = Weights(hour_markup=Decimal("15"))


def _row(n, dep_utc, hours, price, *, source="bahn.de", currency="EUR", transfers=0, offset=0, arr_utc=None):
    """A row of `trip_page()`: one leg from `dep_utc` for `hours`, or to `arr_utc`, with `transfers` changes."""
    arr_utc = arr_utc or dep_utc + timedelta(hours=hours)
    it = Itinerary(fingerprint=f"fp{n}", depart_at=dep_utc, arrive_at=arr_utc, duration_min=hours * 60,
                   transfers=transfers, mode_summary="train")
    it.legs = [Leg(seq=0, mode="train", carrier="DB", from_name="Berlin", to_name="Paris", depart_at=dep_utc,
                   depart_offset_min=offset, arrive_at=arr_utc, arrive_offset_min=offset)]
    fare = Fare(source=source, latest_price=Decimal(price), currency=currency, latest_captured_at=dep_utc)
    fare.itinerary = it
    _, cost = row_cost(it, [fare], [], _WEIGHTS, _NO_STALE)
    return it, fare, cost


def test_four_rows_give_the_three_best_in_the_order_of_the_effective_cost():
    rows = [
        _row(1, datetime(2026, 12, 20, 6, 0, tzinfo=UTC), 4, "90.00"),  # 90 + 4 * 15 = 150
        _row(2, datetime(2026, 12, 20, 7, 0, tzinfo=UTC), 9, "40.00"),  # 40 + 9 * 15 = 175
        _row(3, datetime(2026, 12, 20, 5, 0, tzinfo=UTC), 2, "120.00"),  # 120 + 2 * 15 = 150, departs first
        _row(4, datetime(2026, 12, 20, 8, 0, tzinfo=UTC), 1, "200.00"),  # 200 + 15 = 215: not in the top 3
    ]
    assert trip_summary(rows).split("\n") == [
        "Sun 20 Dec 05:00 → 07:00 · 0 transfers · €120.00 · effective €150.00 · bahn.de",
        "Sun 20 Dec 06:00 → 10:00 · 0 transfers · €90.00 · effective €150.00 · bahn.de",
        "Sun 20 Dec 07:00 → 16:00 · 0 transfers · €40.00 · effective €175.00 · bahn.de",
    ]


def test_a_row_that_arrives_on_the_next_local_day_ends_with_plus_one_day():
    row = _row(1, datetime(2026, 12, 20, 22, 0, tzinfo=UTC), 5, "30.00")
    assert trip_summary([row]) == (
        "Sun 20 Dec 22:00 → 03:00 +1 day · 0 transfers · €30.00 · effective €105.00 · bahn.de"
    )


def test_an_arrival_two_days_later_ends_with_plus_two_days():
    row = _row(1, datetime(2026, 12, 20, 22, 0, tzinfo=UTC), 0, "30.00",
               arr_utc=datetime(2026, 12, 22, 2, 0, tzinfo=UTC))
    assert trip_summary([row]).startswith("Sun 20 Dec 22:00 → 02:00 +2 days · ")


def test_a_row_with_no_transfers_shows_zero_transfers_and_one_transfer_is_singular():
    direct = _row(1, datetime(2026, 12, 20, 9, 0, tzinfo=UTC), 2, "10.00")
    changed = _row(2, datetime(2026, 12, 20, 9, 0, tzinfo=UTC), 2, "10.00", transfers=1)
    lines = trip_summary([direct, changed]).split("\n")
    assert sum(" · 0 transfers · " in line for line in lines) == 1
    assert sum(" · 1 transfer · " in line for line in lines) == 1
    assert all("1 transfers" not in line for line in lines)


def test_the_times_are_the_local_times_of_the_legs():
    # 06:34 UTC at the offset +60 is 07:34 local; the arrival at 14:26 UTC is 15:26 local
    row = _row(1, datetime(2026, 12, 20, 6, 34, tzinfo=UTC), 0, "89.90", offset=60,
               arr_utc=datetime(2026, 12, 20, 14, 26, tzinfo=UTC))
    assert trip_summary([row]).startswith("Sun 20 Dec 07:34 → 15:26 · ")


def test_a_row_with_no_rate_is_not_in_the_text():
    no_rate = _row(1, datetime(2026, 12, 20, 6, 0, tzinfo=UTC), 1, "5.00", currency="CHF")
    rated = _row(2, datetime(2026, 12, 20, 7, 0, tzinfo=UTC), 3, "50.00")
    text = trip_summary([no_rate, rated])
    assert text == "Sun 20 Dec 07:00 → 10:00 · 0 transfers · €50.00 · effective €95.00 · bahn.de"
    assert "CHF" not in text


def test_no_rows_give_an_empty_text():
    assert trip_summary([]) == ""


def test_fewer_than_three_rows_give_one_line_per_row():
    rows = [_row(1, datetime(2026, 12, 20, 6, 0, tzinfo=UTC), 1, "10.00")]
    assert trip_summary(rows).count("\n") == 0
    assert trip_summary(rows).endswith("effective €25.00 · bahn.de")
