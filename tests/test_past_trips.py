"""The past trips of the trips list (#1997)."""

from datetime import date, timedelta

from app.trips import TripRow, past_trips

TODAY = date(2026, 11, 10)


def trip(id: int, date_from: date | None, date_to: date | None, status: str = "open", **kw) -> TripRow:
    return TripRow(
        id=id, title=f"trip {id}", origin_text="A", destination_text="B", date_from=date_from, date_to=date_to,
        status=status, offer_count=0, best_price=None, best_currency=None, **kw,
    )


def ago(days: int) -> date:
    return TODAY - timedelta(days=days)


def test_ended_before_the_cutoff_only():
    rows = [
        trip(1, ago(12), ago(10)),                      # ended 10 days ago
        trip(2, ago(40), ago(30)),                      # ended 30 days ago
        trip(3, TODAY + timedelta(days=30), TODAY + timedelta(days=31)),  # next month
        trip(4, None, None),                            # no date
        trip(5, ago(40), ago(30), status="archived"),   # archived
    ]
    assert past_trips(rows, TODAY) == [1, 2]


def test_round_trip_ends_with_its_return():
    rows = [
        trip(1, ago(12), ago(10)),                                          # outbound ended 10 days ago
        trip(2, TODAY + timedelta(days=2), TODAY + timedelta(days=3), return_of_id=1),  # return in 3 days
    ]
    assert past_trips(rows, TODAY) == []


def test_round_trip_that_ended_gives_both_ids():
    rows = [
        trip(1, ago(20), ago(18)),
        trip(2, ago(15), ago(14), return_of_id=1),
    ]
    assert past_trips(rows, TODAY) == [1, 2]


def test_journey_with_a_trip_without_date_gives_no_id():
    rows = [
        trip(1, ago(20), ago(18)),
        trip(2, None, None, return_of_id=1),
    ]
    assert past_trips(rows, TODAY) == []


def test_split_trip_counts_in_the_journey_end():
    rows = [
        trip(1, ago(20), ago(18)),
        trip(2, ago(5), ago(3), split_of_id=1),  # a part of trip 1 that ended 3 days ago: not past
    ]
    assert past_trips(rows, TODAY) == []


def test_cutoff_is_exclusive_at_the_day_count():
    rows = [
        trip(1, ago(9), ago(7)),  # ended exactly 7 days ago: not before the cutoff
        trip(2, ago(9), ago(8)),  # ended 8 days ago: before the cutoff
    ]
    assert past_trips(rows, TODAY) == [2]


def test_days_argument_changes_the_cutoff():
    rows = [trip(1, ago(12), ago(10))]
    assert past_trips(rows, TODAY, days=14) == []
    assert past_trips(rows, TODAY, days=3) == [1]


def test_no_rows_gives_no_ids():
    assert past_trips([], TODAY) == []
