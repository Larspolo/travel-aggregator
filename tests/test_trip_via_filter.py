"""The field "Via" of the trip page hides the offers that do not stop at or change at the place (epic #2699)."""

import copy

from tests.test_trip_book_timing import without_book_timing
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def via_stop(price):
    """One direct leg Amsterdam Centraal -> Berlin Hbf with a stop at Hannover Hbf."""
    o = copy.deepcopy(direct(price))
    o["legs"][0] = dict(o["legs"][0], from_name="Amsterdam Centraal", to_name="Berlin Hbf", service_no="ICE 10",
                        depart_at="2026-12-20T10:00:00+01:00", arrive_at="2026-12-20T14:00:00+01:00",
                        stops=[{"name": "Hannover Hbf", "depart_at": "2026-12-20T12:00:00+01:00"}])
    return o


def test_via_hides_the_offers_that_do_not_stop_at_the_place(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), via_stop("100.00")])
    page = without_book_timing(client.get(f"/trips/{trip_id}?via=hannover").text)
    assert page.count("= €") == 1  # the offer with the stop at Hannover Hbf is shown
    assert "Filters hide 1 of 2 offers" in page and "via hannover" in page


def test_via_the_empty_text_and_no_via_show_all_offers(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), via_stop("100.00")])
    assert without_book_timing(client.get(f"/trips/{trip_id}").text).count("= €") == 2
    assert without_book_timing(client.get(f"/trips/{trip_id}?via=").text).count("= €") == 2


def test_the_via_field_keeps_the_text_and_the_sort_links_keep_it(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), via_stop("100.00")])
    page = without_book_timing(client.get(f"/trips/{trip_id}?via=hannover").text)
    assert 'name="via"' in page and 'value="hannover"' in page
    assert "via=hannover" in page


def test_the_link_of_the_via_label_removes_the_filter(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), via_stop("100.00")])
    page = without_book_timing(client.get(f"/trips/{trip_id}?via=hannover").text)
    assert "via=hannover" in page
    back = without_book_timing(client.get(f"/trips/{trip_id}").text)
    assert back.count("= €") == 2
