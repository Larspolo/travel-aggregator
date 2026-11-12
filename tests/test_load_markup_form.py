"""The expected load markups in "Advanced" (#2609, epic #2607): the trip page and the profile page."""

import re

from app import tokens
from tests.test_mode_hours_form import _value
from tests.test_trip_page import ingest, offer
from tests.test_trip_booked import trip  # noqa: F401 (fixture)


def test_advanced_shows_both_load_fields_at_zero(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}").text
    assert "Expected load high €" in page
    assert "Expected load very high €" in page
    assert _value(page, "load_high_markup") == "0"
    assert _value(page, "load_very_high_markup") == "0"


def test_a_url_value_fills_the_very_high_field(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}", params={"load_very_high_markup": "8"}).text
    assert _value(page, "load_very_high_markup") == "8"


def test_a_value_over_1000_is_an_error(trip):  # noqa: F811
    client, trip_id = trip
    assert client.get(f"/trips/{trip_id}", params={"load_high_markup": "1001"}).status_code == 422


def test_a_saved_profile_keeps_the_very_high_value_and_shows_it_again(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get("/profiles/new").text
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post("/profiles/new", data={"csrf_token": token, "name": "L", "load_very_high_markup": "8"},
                    follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/profiles").text
    profile_id = re.search(r'<strong>L</strong>.*?href="/profiles/(\d+)"', page, re.S).group(1)
    assert _value(client.get(f"/profiles/{profile_id}").text, "load_very_high_markup") == "8"


def test_the_trip_page_shows_the_very_high_part_for_a_leg_at_level_3(trip, sessions):  # noqa: F811
    client, trip_id = trip
    with sessions() as s:
        token = tokens.create(s, "load")
    o = offer("89.90")
    for leg in o["legs"]:
        leg["load_second"] = 3
    ingest(client, {"Authorization": f"Bearer {token}"}, trip_id, [o])
    page = client.get(f"/trips/{trip_id}", params={"load_very_high_markup": "8"}).text
    assert "expected load very high" in page
    assert "expected load very high" not in client.get(f"/trips/{trip_id}").text
