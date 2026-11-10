"""The transfer place markups in the "Advanced" form of the trip page and the profiles page (#1851)."""

import re

from app.models import ScoreProfile
from app.profiles import from_config
from tests.test_trip_booked import csrf
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _profiles(sessions):
    with sessions() as s:
        return [(p.name, p.config_json) for p in s.query(ScoreProfile).order_by(ScoreProfile.id)]


def _two(client, auth, trip_id):
    other = offer("110.00", "ICE 9")
    other["legs"][0]["to_name"] = other["legs"][1]["from_name"] = "Mannheim Hbf"
    ingest(client, auth, trip_id, [offer("100.00", "ICE 1"), other])


def test_advanced_shows_the_rows_with_the_saved_values(trip):  # noqa: F811
    client, auth, trip_id = trip
    _two(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    for i in "123":
        assert f'name="transfer_place{i}_name" maxlength="100" value=""' in page
        assert f'name="transfer_place{i}_markup" min="-1000" max="1000" step="0.01" value="0"' in page


def test_a_transfer_place_markup_re_ranks_the_table(trip):  # noqa: F811
    client, auth, trip_id = trip
    _two(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert page.index("ICE 1") < page.index("ICE 9")
    page = client.get(f"/trips/{trip_id}?transfer_place2_name=Basel&transfer_place2_markup=15").text
    assert page.index("ICE 9") < page.index("ICE 1")
    assert 'name="transfer_place2_name" maxlength="100" value="Basel"' in page


def test_bad_values_in_the_url_give_an_error(trip):  # noqa: F811
    client, _, trip_id = trip
    assert client.get(f"/trips/{trip_id}?transfer_place1_markup=5000").status_code == 422
    assert client.get(f"/trips/{trip_id}?transfer_place1_name={'x' * 101}").status_code == 422
    assert client.get(f"/trips/{trip_id}?transfer_place1_name={'x' * 100}").status_code == 200


def test_save_as_profile_keeps_the_values_and_a_bad_value_saves_nothing(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    token = csrf(client, trip_id)
    base = {"csrf_token": token, "trip_id": trip_id}
    for bad in ({"transfer_place1_markup": "5000"}, {"transfer_place2_name": "x" * 101}):
        assert client.post("/profiles", data={**base, "name": "Bad", **bad}).status_code == 422
    assert _profiles(sessions) == []
    data = {**base, "name": "Places", "transfer_place1_name": "x" * 100, "transfer_place3_name": "Basel",
            "transfer_place3_markup": "-5.50"}
    assert client.post("/profiles", data=data, follow_redirects=False).status_code == 303
    w = from_config(_profiles(sessions)[0][1])
    assert (w.transfer_place1_name, w.transfer_place3_name, str(w.transfer_place3_markup)) == ("x" * 100, "Basel", "-5.50")


def test_the_profiles_page_has_the_rows_and_rejects_a_long_name(trip, sessions):  # noqa: F811
    client, _, _ = trip
    page = client.get("/profiles/new").text
    assert 'name="transfer_place1_name" maxlength="100" value=""' in page
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post("/profiles/new", data={"csrf_token": token, "name": "P", "transfer_place1_name": "x" * 101})
    assert r.status_code == 422 and "longer than 100 characters; nothing changed" in r.text
    assert _profiles(sessions) == []
