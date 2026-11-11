"""The transfer wait hour value in "Advanced" (#2221, epic #2219): the trip page and the profile page."""

import re

from tests.test_mode_hours_form import _value
from tests.test_trip_booked import trip  # noqa: F401 (fixture)


def test_advanced_shows_the_transfer_wait_field_empty(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}").text
    assert "Transfer wait hour €" in page
    assert _value(page, "transfer_wait_hour_markup") == ""


def test_a_url_value_fills_the_field_and_a_blank_gives_the_hour_markup(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}", params={"transfer_wait_hour_markup": "25"}).text
    assert _value(page, "transfer_wait_hour_markup") == "25"
    assert "transfer_wait_hour_markup=25" in page  # the sort links keep the value
    page = client.get(f"/trips/{trip_id}", params={"transfer_wait_hour_markup": ""}).text
    assert _value(page, "transfer_wait_hour_markup") == ""


def test_the_value_101_is_an_error_as_on_the_train_hour(trip):  # noqa: F811
    client, trip_id = trip
    assert client.get(f"/trips/{trip_id}", params={"train_hour_markup": "101"}).status_code == 422
    assert client.get(f"/trips/{trip_id}", params={"transfer_wait_hour_markup": "101"}).status_code == 422


def test_the_profile_page_shows_and_validates_the_field(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get("/profiles/new").text
    assert "Transfer wait hour €" in page and _value(page, "transfer_wait_hour_markup") == ""
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post("/profiles/new", data={"csrf_token": token, "name": "Z", "transfer_wait_hour_markup": "101"})
    assert "transfer_wait_hour_markup" in r.text and "101" in r.text
