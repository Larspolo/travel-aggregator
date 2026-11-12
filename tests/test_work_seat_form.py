"""The work-seat hour value in "Advanced" (#2566, epic #2565): the trip page and the profile page."""

import re

from app import tokens
from tests.test_mode_hours_form import _value
from tests.test_trip_page import ingest, offer
from tests.test_trip_booked import trip  # noqa: F401 (fixture)


def test_advanced_shows_the_work_seat_field_empty(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}").text
    assert "Each work-seat hour €" in page
    assert _value(page, "work_seat_hour_markup") == ""


def test_a_url_value_fills_the_field_and_a_blank_stays_empty(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}", params={"work_seat_hour_markup": "5"}).text
    assert _value(page, "work_seat_hour_markup") == "5"
    page = client.get(f"/trips/{trip_id}", params={"work_seat_hour_markup": ""}).text
    assert _value(page, "work_seat_hour_markup") == ""


def test_the_value_101_is_an_error(trip):  # noqa: F811
    client, trip_id = trip
    assert client.get(f"/trips/{trip_id}", params={"work_seat_hour_markup": "101"}).status_code == 422


def test_a_saved_profile_keeps_the_value_and_shows_it_again(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get("/profiles/new").text
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post("/profiles/new", data={"csrf_token": token, "name": "S", "work_seat_hour_markup": "5"},
                    follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/profiles").text
    profile_id = re.search(r'<strong>S</strong>.*?href="/profiles/(\d+)"', page, re.S).group(1)
    assert _value(client.get(f"/profiles/{profile_id}").text, "work_seat_hour_markup") == "5"


def test_the_trip_page_shows_the_work_seat_part_for_wifi_and_power(trip, sessions):  # noqa: F811
    client, trip_id = trip
    with sessions() as s:
        token = tokens.create(s, "seat")
    o = offer("89.90")
    for leg in o["legs"]:
        leg["services"] = ["wifi", "power"]
    ingest(client, {"Authorization": f"Bearer {token}"}, trip_id, [o])
    page = client.get(f"/trips/{trip_id}", params={"work_seat_hour_markup": "5"}).text
    assert "work seat" in page
    assert "work seat" not in client.get(f"/trips/{trip_id}").text
