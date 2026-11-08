"""The split trips under their trip on the trips list (#1180)."""

from decimal import Decimal

from app.models import Trip
from app.trips import TripRow, archived_journeys, in_journeys
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)


def _row(id_, title, o, d, price=None, return_of=None, split_of=None, status="planning"):
    return TripRow(id=id_, title=title, origin_text=o, destination_text=d, date_from=None, date_to=None,
                   status=status, offer_count=0, best_price=price, best_currency="EUR" if price else None,
                   return_of_id=return_of, split_of_id=split_of)


ROWS = [_row(1, "Amsterdam → Zürich", "Amsterdam", "Zürich", Decimal("100")),
        _row(2, "Amsterdam → Köln", "Amsterdam", "Köln", Decimal("40"), split_of=1),
        _row(3, "Köln → Zürich", "Köln", "Zürich", Decimal("50"), split_of=1),
        _row(4, "Zürich → Amsterdam", "Zürich", "Amsterdam", Decimal("90"), return_of=1)]


def test_the_split_trips_follow_their_trip_and_add_nothing_to_the_total():
    lines = [(k, t.id, n) for k, t, n in in_journeys(ROWS)]
    assert lines == [("trip", 1, ""), ("split", 2, "Köln"), ("split", 3, "Köln"),
                     ("return", 4, "Amsterdam → Zürich"), ("total", 4, "EUR 190")]


def test_archive_keeps_the_split_trips_with_their_trip():
    rows = [_row(1, "A", "A", "B", status="archived"), _row(2, "A → X", "A", "X", split_of=1)]
    assert [t.id for _, t, _ in archived_journeys(rows, True)] == [1, 2]
    assert archived_journeys(rows, False) == []


def test_the_pages_show_the_split_and_the_link_back(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    with sessions() as s:
        trip = s.get(Trip, trip_id)
        trip.title, trip.origin_text, trip.destination_text = "Amsterdam → Zürich", "Amsterdam", "Zürich"
        s.commit()
    c.post(f"/trips/{trip_id}/split", data={"via": "Köln"}, headers={"X-CSRF-Token": _csrf(c, "/settings")})
    page = c.get("/").text
    assert page.count("split via Köln") == 2
    assert page.index("Amsterdam → Zürich") < page.index("split via Köln")
    with sessions() as s:
        split_id = s.get(Trip, trip_id).split_trips[0].id
    assert f'Part of <a href="/trips/{trip_id}">Amsterdam → Zürich</a>' in c.get(f"/trips/{split_id}").text
