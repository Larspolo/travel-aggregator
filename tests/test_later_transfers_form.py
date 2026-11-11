"""The later-transfer markup in "Advanced" (#2303, epic #2301): the trip page and the profile page."""

import re

from tests.test_mode_hours_form import _value
from tests.test_trip_booked import trip  # noqa: F401 (fixture)


def test_advanced_shows_the_later_transfer_field_empty(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}").text
    assert "Each later transfer €" in page
    assert _value(page, "later_transfer_markup") == ""


def test_a_url_value_fills_the_field_and_a_blank_stays_empty(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}", params={"later_transfer_markup": "25"}).text
    assert _value(page, "later_transfer_markup") == "25"
    assert "later_transfer_markup=25" in page  # the sort links keep the value
    page = client.get(f"/trips/{trip_id}", params={"later_transfer_markup": ""}).text
    assert _value(page, "later_transfer_markup") == ""


def test_the_value_101_is_an_error(trip):  # noqa: F811
    client, trip_id = trip
    assert client.get(f"/trips/{trip_id}", params={"later_transfer_markup": "101"}).status_code == 422


def test_the_profile_page_shows_and_validates_the_field(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get("/profiles/new").text
    assert "Each later transfer €" in page and _value(page, "later_transfer_markup") == ""
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post("/profiles/new", data={"csrf_token": token, "name": "Z", "later_transfer_markup": "101"})
    assert "later_transfer_markup" in r.text and "101" in r.text
