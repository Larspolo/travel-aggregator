"""The count of rows with an estimated part on the trip page (#2053)."""

from decimal import Decimal
from types import SimpleNamespace

from app.door import estimate_count, has_place_gap
from app.web.pages import templates
from tests.test_bag_estimate import _flight
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _row(*labels):
    return (None, None, SimpleNamespace(extras=tuple((label, Decimal(0)) for label in labels)))


def _html(rows):
    return templates.get_template("trip_estimates.html").render(
        estimates=estimate_count(rows), estimate_places=has_place_gap(rows))


def test_two_flights_with_no_bag_data_and_a_train():
    rows = [_row("airport time", "baggage (estimate)"), _row("baggage (estimate)"), _row()]
    assert estimate_count(rows) == 2
    html = _html(rows)
    assert "2 rows have an estimate in the breakdown" in html
    assert "/places" not in html


def test_no_estimate_gives_no_line():
    rows = [_row("baggage", "access time"), _row("baggage (included)"), _row()]
    assert estimate_count(rows) == 0
    assert _html(rows).strip() == ""


def test_place_gap_gives_the_link():
    rows = [_row("no egress place for Zürich Flughafen")]
    html = _html(rows)
    assert "1 row has an estimate in the breakdown" in html
    assert 'href="/places"' in html
    assert estimate_count([_row("no access place for Basel", "baggage (estimate)")]) == 1


def test_trip_page_counts_two_flights_and_not_the_train(trip):  # noqa: F811
    client, auth, trip_id = trip
    assert "an estimate in the breakdown" not in client.get(f"/trips/{trip_id}?baggage_fee=30").text
    ingest(client, auth, trip_id, [_flight("100.00", "KL 1"), _flight("120.00", "KL 2"), direct("90.00")])
    page = client.get(f"/trips/{trip_id}?baggage_fee=30").text
    assert "2 rows have an estimate in the breakdown" in page
    assert 'href="/places">Places' not in page
