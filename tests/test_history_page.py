"""The price history (#240, #649): a direct visit is a page with its header; htmx (HX-Request) gets the fragment."""

from tests.test_history_whole import capture, itinerary_id, trip  # noqa: F401  (trip is a fixture)


def test_a_direct_visit_is_a_page_with_one_header(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    capture(client, auth, trip_id, "89.90", "2026-11-03T19:41:00Z")
    it = itinerary_id(sessions, trip_id)
    page = client.get(f"/trips/{trip_id}/itineraries/{it}/history").text
    assert '<header class="page-header">' in page and page.count("<h1") == 1
    assert f'href="/trips/{trip_id}"' in page and "Back to the trip" in page


def test_htmx_gets_the_fragment_without_a_page(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    capture(client, auth, trip_id, "89.90", "2026-11-03T19:41:00Z")
    it = itinerary_id(sessions, trip_id)
    fragment = client.get(f"/trips/{trip_id}/itineraries/{it}/history", headers={"HX-Request": "true"}).text
    assert "<html" not in fragment and "<h1" not in fragment
    assert '<table class="history">' in fragment
