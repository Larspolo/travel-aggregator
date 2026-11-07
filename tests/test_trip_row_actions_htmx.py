"""Pin, Hide and Booked with htmx (#666): an htmx POST gets the table with the new state, not a redirect; a normal
POST still gets 303 to the trip page."""

import pytest

from tests.test_trip_pin import _cheap_id, csrf, trip  # noqa: F401  (trip is a fixture)


@pytest.mark.parametrize("action, text", [("pin", "pinned"), ("hide", "Unhide"), ("booked", "badge booked")])
def test_an_htmx_post_returns_the_table_with_the_new_state(trip, sessions, action, text):  # noqa: F811
    client, trip_id = trip
    cheap = _cheap_id(sessions, trip_id)
    token = csrf(client, trip_id)
    url = f"/trips/{trip_id}/itineraries/{cheap}/{action}"
    query = "?show_hidden=true" if action == "hide" else ""  # the view of the page: a hidden row stays visible
    r = client.post(url + query, data={"csrf_token": token}, headers={"HX-Request": "true"}, follow_redirects=False)
    assert r.status_code == 200
    assert '<tbody id="rows">' in r.text and "<html" not in r.text
    assert text in r.text


@pytest.mark.parametrize("action", ["pin", "hide", "booked"])
def test_a_normal_post_still_redirects(trip, sessions, action):  # noqa: F811
    client, trip_id = trip
    cheap = _cheap_id(sessions, trip_id)
    r = client.post(f"/trips/{trip_id}/itineraries/{cheap}/{action}", data={"csrf_token": csrf(client, trip_id)},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{trip_id}"
