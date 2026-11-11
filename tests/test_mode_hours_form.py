"""The hour values per mode in "Advanced" (#1568): the trip page, the live re-ranking and "Save as profile"."""

import re

from app.models import ScoreProfile
from tests.test_trip_booked import csrf, trip  # noqa: F401 (fixture)

FIELDS = ("train_hour_markup", "bus_hour_markup", "flight_hour_markup", "ferry_hour_markup")


def _value(page, name):
    return re.search(rf'name="{name}"[^>]*value="([^"]*)"', page).group(1)


def test_advanced_shows_four_empty_fields_with_a_placeholder(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}").text
    for label in ("Train hour €", "Bus hour €", "Flight hour €", "Ferry hour €"):
        assert label in page
    for name in FIELDS:
        assert _value(page, name) == ""
    assert page.count('placeholder="the hour markup"') >= 4


def test_a_url_value_fills_the_field_and_a_blank_gives_the_hour_markup(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}", params={"train_hour_markup": "40"}).text
    assert _value(page, "train_hour_markup") == "40"
    assert "train_hour_markup=40" in page  # the sort links keep the value
    page = client.get(f"/trips/{trip_id}", params={"train_hour_markup": ""}).text
    assert _value(page, "train_hour_markup") == ""


def test_an_out_of_range_url_value_is_an_error(trip):  # noqa: F811
    client, trip_id = trip
    for bad in ("150", "-1", "abc", "NaN"):
        assert client.get(f"/trips/{trip_id}", params={"bus_hour_markup": bad}).status_code == 422


def test_save_as_profile_keeps_the_values_and_rejects_150_and_minus_1(trip, sessions):  # noqa: F811
    client, trip_id = trip
    token = csrf(client, trip_id)
    for bad in ("150", "-1"):
        r = client.post("/profiles", data={"csrf_token": token, "trip_id": trip_id, "name": "X",
                                           "flight_hour_markup": bad})
        assert r.status_code == 422
    with sessions() as s:
        assert s.query(ScoreProfile).count() == 0
    client.post("/profiles", data={"csrf_token": token, "trip_id": trip_id, "name": "Fast",
                                   "train_hour_markup": "5", "ferry_hour_markup": ""})
    with sessions() as s:
        p = s.query(ScoreProfile).one()
        assert p.config_json["train_hour_markup"] == "5" and p.config_json["ferry_hour_markup"] is None
        pid = p.id
    page = client.get(f"/trips/{trip_id}", params={"profile": pid}).text
    assert _value(page, "train_hour_markup") == "5" and _value(page, "ferry_hour_markup") == ""
    # a blank field overrides the saved value of the profile: None, the hour markup
    page = client.get(f"/trips/{trip_id}", params={"profile": pid, "train_hour_markup": ""}).text
    assert _value(page, "train_hour_markup") == ""


def test_the_profile_page_form_validates_the_range(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get("/profiles/new").text
    assert "Train hour €" in page and _value(page, "train_hour_markup") == ""
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post("/profiles/new", data={"csrf_token": token, "name": "Y", "bus_hour_markup": "150"})
    assert "bus_hour_markup: 150 is not in 0 to 100" in r.text


