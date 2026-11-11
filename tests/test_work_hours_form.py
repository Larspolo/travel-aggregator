"""The work-hour markup in "Advanced" (#2333, epic #2331): the trip page and the profile page."""

import re

from app import tokens
from tests.test_mode_hours_form import _value
from tests.test_trip_page import ingest, offer
from tests.test_trip_booked import trip  # noqa: F401 (fixture)


def test_advanced_shows_the_work_hour_fields(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}").text
    assert "Each work hour €" in page
    assert _value(page, "work_hour_markup") == ""
    assert _value(page, "work_hour_start") == "9"
    assert _value(page, "work_hour_end") == "17"


def test_a_url_value_fills_the_field_and_a_blank_stays_empty(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}", params={"work_hour_markup": "30"}).text
    assert _value(page, "work_hour_markup") == "30"
    assert "work_hour_markup=30" in page  # the sort links keep the value
    page = client.get(f"/trips/{trip_id}", params={"work_hour_markup": ""}).text
    assert _value(page, "work_hour_markup") == ""


def test_the_value_101_is_an_error(trip):  # noqa: F811
    client, trip_id = trip
    assert client.get(f"/trips/{trip_id}", params={"work_hour_markup": "101"}).status_code == 422


def test_the_profile_page_shows_and_validates_the_fields(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get("/profiles/new").text
    assert "Each work hour €" in page and _value(page, "work_hour_markup") == ""
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post("/profiles/new", data={"csrf_token": token, "name": "Z", "work_hour_markup": "101"})
    assert "work_hour_markup" in r.text and "101" in r.text


def test_the_hours_must_be_whole_numbers_in_range(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get("/profiles/new").text
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post("/profiles/new", data={"csrf_token": token, "name": "Y", "work_hour_start": "8.5"})
    assert r.status_code == 422 and "work_hour_start" in r.text


def _save(client, name, data):
    page = client.get("/profiles/new").text
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    return client.post("/profiles/new", data={"csrf_token": token, "name": name, **data}, follow_redirects=False)


def test_a_saved_profile_keeps_the_hours_and_shows_them_again(trip):  # noqa: F811
    client, trip_id = trip
    assert _save(client, "H", {"work_hour_markup": "30", "work_hour_start": "8", "work_hour_end": "18"}).status_code == 303
    page = client.get("/profiles").text
    profile_id = re.search(r'<strong>H</strong>.*?href="/profiles/(\d+)"', page, re.S).group(1)
    edit = client.get(f"/profiles/{profile_id}").text
    assert _value(edit, "work_hour_markup") == "30"
    assert _value(edit, "work_hour_start") == "8"
    assert _value(edit, "work_hour_end") == "18"


def test_a_wrong_pair_of_hours_gives_the_defaults(trip):  # noqa: F811
    client, trip_id = trip
    assert _save(client, "X", {"work_hour_markup": "30", "work_hour_start": "18", "work_hour_end": "8"}).status_code == 303
    page = client.get("/profiles").text
    profile_id = re.search(r'<strong>X</strong>.*?href="/profiles/(\d+)"', page, re.S).group(1)
    edit = client.get(f"/profiles/{profile_id}").text
    assert _value(edit, "work_hour_start") == "9"
    assert _value(edit, "work_hour_end") == "17"


def test_the_trip_page_shows_the_work_hours_part(trip, sessions):  # noqa: F811
    client, trip_id = trip
    with sessions() as s:
        token = tokens.create(s, "work")
    o = offer("89.90")  # a leg on Monday 21 Dec 2026, 07:34 to 15:26: work hours 9 to 15 (#2333)
    for leg in o["legs"]:
        leg["depart_at"] = leg["depart_at"].replace("2026-12-20", "2026-12-21")
        leg["arrive_at"] = leg["arrive_at"].replace("2026-12-20", "2026-12-21")
    ingest(client, {"Authorization": f"Bearer {token}"}, trip_id, [o])
    page = client.get(f"/trips/{trip_id}", params={"work_hour_markup": "30"}).text
    assert "work hours" in page
    assert "work hours" not in client.get(f"/trips/{trip_id}").text
