"""A journey whose first trip is archived gives no past trip (#2009)."""

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


def test_archived_first_trip_gives_no_past_trip_of_its_journey():
    rows = [
        trip(1, ago(20), ago(18), status="archived"),
        trip(2, ago(15), ago(14), return_of_id=1),
    ]
    assert past_trips(rows, TODAY) == []


def test_open_first_trip_with_archived_return_gives_the_first_trip_only():
    rows = [
        trip(1, ago(20), ago(18)),
        trip(2, ago(15), ago(14), status="archived", return_of_id=1),
    ]
    assert past_trips(rows, TODAY) == [1]
