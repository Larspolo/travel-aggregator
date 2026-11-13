"""The field "Avoid" of the trip page hides the offers that stop at or change at the place (epic #2719)."""

from tests.test_trip_book_timing import without_book_timing
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct
from tests.test_trip_via_filter import via_stop


def test_avoid_hides_the_offers_that_stop_at_the_place(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), via_stop("100.00")])
    page = without_book_timing(client.get(f"/trips/{trip_id}?avoid=hannover").text)
    assert page.count("= €") == 1  # the direct offer with no stop at Hannover Hbf is shown
    assert "Filters hide 1 of 2 offers" in page and "avoid hannover</a> hides 1" in page
    assert "avoid=hannover" in page


def test_avoid_the_empty_text_and_no_avoid_show_all_offers(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), via_stop("100.00")])
    assert without_book_timing(client.get(f"/trips/{trip_id}").text).count("= €") == 2
    assert without_book_timing(client.get(f"/trips/{trip_id}?avoid=").text).count("= €") == 2


def test_the_avoid_field_keeps_the_text_and_the_sort_links_keep_it(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), via_stop("100.00")])
    page = without_book_timing(client.get(f"/trips/{trip_id}?avoid=hannover").text)
    assert 'name="avoid"' in page and 'value="hannover"' in page
    assert "avoid=hannover" in page


def test_the_link_of_the_avoid_label_removes_the_filter(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), via_stop("100.00")])
    page = without_book_timing(client.get(f"/trips/{trip_id}?avoid=hannover").text)
    assert "avoid=hannover" in page
    back = without_book_timing(client.get(f"/trips/{trip_id}").text)
    assert back.count("= €") == 2


def test_via_and_avoid_the_same_place_show_no_offer(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [direct("150.00"), via_stop("100.00")])
    page = without_book_timing(client.get(f"/trips/{trip_id}?via=hannover&avoid=hannover").text)
    assert page.count("= €") == 0
