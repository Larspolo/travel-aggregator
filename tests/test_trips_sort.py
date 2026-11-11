"""The sort of the journeys of the trips list (#1972)."""

from datetime import datetime, timezone
from decimal import Decimal

from app.trips import TripRow, in_journeys, sort_journeys


def _trip(id, title, price=None, currency="EUR", no_rate=False, return_of_id=None):
    return TripRow(id=id, title=title, origin_text=None, destination_text=None, date_from=None, date_to=None,
                   status="planning", offer_count=1 if price is not None else 0,
                   best_price=Decimal(str(price)) if price is not None else None,
                   best_currency=currency if price is not None else None,
                   return_of_id=return_of_id, no_rate=no_rate)


def _ids(lines):
    return [t.id for kind, t, _ in lines if kind != "total"]


def test_price_puts_the_lowest_first_and_no_offer_last():
    lines = in_journeys([_trip(1, "A", 40), _trip(2, "B"), _trip(3, "C", 25)])
    assert _ids(sort_journeys(lines, "price", {})) == [3, 1, 2]


def test_price_puts_a_trip_with_no_rate_after_the_eur_prices():
    lines = in_journeys([_trip(1, "A", 900, currency="USD", no_rate=True), _trip(2, "B", 40), _trip(3, "C", 50)])
    assert _ids(sort_journeys(lines, "price", {})) == [2, 3, 1]


def test_capture_puts_the_newest_first_and_no_capture_last():
    lines = in_journeys([_trip(1, "A"), _trip(2, "B"), _trip(3, "C")])
    captured = {1: datetime(2026, 11, 1, tzinfo=timezone.utc), 3: datetime(2026, 11, 9, tzinfo=timezone.utc)}
    assert _ids(sort_journeys(lines, "capture", captured)) == [3, 1, 2]


def test_title_sorts_a_to_z_with_no_case_and_no_diacritics():
    lines = in_journeys([_trip(1, "zürich"), _trip(2, "Amsterdam"), _trip(3, "Ápeldoorn")])
    assert [t.title for kind, t, _ in sort_journeys(lines, "title", {}) if kind == "trip"] == [
        "Amsterdam", "Ápeldoorn", "zürich"]


def test_a_journey_stays_whole_and_in_its_order_in_each_sort():
    lines = in_journeys([_trip(1, "Zürich", 60), _trip(2, "Amsterdam", 30, return_of_id=1), _trip(3, "Basel", 10)])
    captured = {1: datetime(2026, 11, 1, tzinfo=timezone.utc), 3: datetime(2026, 11, 9, tzinfo=timezone.utc)}
    for key in ("price", "capture", "title"):
        out = sort_journeys(lines, key, captured)
        assert sorted(map(repr, out)) == sorted(map(repr, lines))
        i = out.index(lines[0])  # the first trip of the journey
        assert out[i:i + 3] == lines[0:3]
        assert out[i + 2][0] == "total"


def test_an_unknown_key_keeps_the_order():
    lines = in_journeys([_trip(1, "B", 40), _trip(2, "A", 10)])
    assert sort_journeys(lines, "nonsense", {}) == lines
    assert sort_journeys(lines, "date", {}) == lines
