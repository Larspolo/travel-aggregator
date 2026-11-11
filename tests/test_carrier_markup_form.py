"""The carrier markups in the "Advanced" form of the trip page and the profiles page (#1531)."""

import re

from app.models import ScoreProfile
from app.profiles import from_config
from tests.test_trip_booked import csrf
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _profiles(sessions):
    with sessions() as s:
        return [(p.name, p.config_json) for p in s.query(ScoreProfile).order_by(ScoreProfile.id)]


def _two(client, auth, trip_id):
    ingest(client, auth, trip_id, [offer("100.00", "FR 1", carrier="Ryanair"), offer("110.00", "KL 2", carrier="KLM")])


def test_advanced_shows_the_rows_and_the_carriers_of_the_trip(trip):  # noqa: F811
    client, auth, trip_id = trip
    _two(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    for i in "123":
        assert f'name="carrier{i}_name" maxlength="50" list="carrier-names"' in page
        assert f'name="carrier{i}_markup" min="-1000" max="1000" step="0.01"' in page
    names = re.search(r'<datalist id="carrier-names">(.*?)</datalist>', page).group(1)
    assert '<option value="KLM">' in names and '<option value="Ryanair">' in names


def test_a_carrier_markup_re_ranks_the_table(trip):  # noqa: F811
    client, auth, trip_id = trip
    _two(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert page.index("FR 1") < page.index("KL 2")
    page = client.get(f"/trips/{trip_id}?carrier1_name=Ryanair&carrier1_markup=15").text
    assert page.index("KL 2") < page.index("FR 1")
    assert 'name="carrier1_name" maxlength="50" list="carrier-names" value="Ryanair"' in page


def test_bad_values_in_the_url_give_an_error(trip):  # noqa: F811
    client, _, trip_id = trip
    assert client.get(f"/trips/{trip_id}?carrier1_markup=5000").status_code == 422
    assert client.get(f"/trips/{trip_id}?carrier1_name={'x' * 51}").status_code == 422


def test_save_as_profile_keeps_the_values_and_a_bad_value_saves_nothing(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    token = csrf(client, trip_id)
    base = {"csrf_token": token, "trip_id": trip_id}
    for bad in ({"carrier1_markup": "5000"}, {"carrier2_name": "x" * 51}):
        assert client.post("/profiles", data={**base, "name": "Bad", **bad}).status_code == 422
    assert _profiles(sessions) == []
    data = {**base, "name": "Airlines", "carrier1_name": "Ryanair", "carrier1_markup": "15", "carrier3_name": "KLM",
            "carrier3_markup": "-5.50"}
    assert client.post("/profiles", data=data, follow_redirects=False).status_code == 303
    w = from_config(_profiles(sessions)[0][1])
    assert (w.carrier1_name, str(w.carrier1_markup), w.carrier3_name, str(w.carrier3_markup)) == (
        "Ryanair", "15", "KLM", "-5.50")


def test_the_profiles_page_has_the_rows_and_rejects_a_long_name(trip, sessions):  # noqa: F811
    client, _, _ = trip
    page = client.get("/profiles/new").text
    assert 'name="carrier1_name" maxlength="50" value=""' in page and "carrier-names" not in page
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post("/profiles/new", data={"csrf_token": token, "name": "P", "carrier1_name": "x" * 51})
    assert r.status_code == 422 and "longer than 50 characters; nothing changed" in r.text
    assert _profiles(sessions) == []
