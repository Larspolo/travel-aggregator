"""The high notice markup in "Advanced" (#2696, epic #2694): the trip page and the profile page."""

import re

from app import tokens
from tests.test_mode_hours_form import _value
from tests.test_trip_page import ingest, offer
from tests.test_trip_booked import trip  # noqa: F401 (fixture)


def test_advanced_shows_the_notice_field_at_zero(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get("/profiles/new").text
    assert "Notice of the operator, high €" in page
    assert _value(page, "notice_markup") == "0"


def test_a_url_value_fills_the_notice_field(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}", params={"notice_markup": "15"}).text
    assert _value(page, "notice_markup") == "15"


def test_a_value_over_1000_is_an_error(trip):  # noqa: F811
    client, trip_id = trip
    assert client.get(f"/trips/{trip_id}", params={"notice_markup": "1001"}).status_code == 422


def test_a_saved_profile_keeps_the_notice_value_and_shows_it_again(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get("/profiles/new").text
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post("/profiles/new", data={"csrf_token": token, "name": "N", "notice_markup": "15"},
                    follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/profiles").text
    profile_id = re.search(r'<strong>N</strong>.*?href="/profiles/(\d+)"', page, re.S).group(1)
    assert _value(client.get(f"/profiles/{profile_id}").text, "notice_markup") == "15"


def test_the_trip_page_shows_the_notice_part_for_a_high_notice(trip, sessions):  # noqa: F811
    client, trip_id = trip
    with sessions() as s:
        token = tokens.create(s, "notice")
    o = offer("89.90")
    o["notices"] = [{"text": "Track repairs", "level": "high", "leg": 0}]
    ingest(client, {"Authorization": f"Bearer {token}"}, trip_id, [o])
    page = client.get(f"/trips/{trip_id}", params={"notice_markup": "15"}).text
    assert "notice: Track repairs" in page
    assert "notice: Track repairs" not in client.get(f"/trips/{trip_id}").text
