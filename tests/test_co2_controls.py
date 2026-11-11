"""The CO₂ controls in "Advanced" (#1417): a price per kg and the kg per hour of each mode."""

import re

from app.models import ScoreProfile
from app.profiles import from_config
from tests.test_trip_booked import csrf, trip  # noqa: F401 (fixture)

GUARDS = ("app/web/templates/weights_advanced.html",)
FIELDS = {"co2_price_kg": "0.25", "co2_train_kg_h": "4.5", "co2_bus_kg_h": "1.5", "co2_flight_kg_h": "80",
          "co2_ferry_kg_h": "6"}


def _fieldset(html):
    return re.search(r"<fieldset><legend>CO₂</legend>.*?</fieldset>", html, flags=re.S).group(0)


def test_advanced_has_a_co2_fieldset_after_modes_with_five_fields(trip):  # noqa: F811
    client, trip_id = trip
    html = client.get(f"/trips/{trip_id}").text
    assert html.index("<legend>Modes</legend>") < html.index("<legend>CO₂</legend>")
    box = _fieldset(html)
    assert re.findall(r'name="([^"]+)"', box) == list(FIELDS)
    assert 'name="co2_price_kg" min="0" max="10" step="0.01"' in box
    for label in ("CO₂ price € per kg", "Train kg CO₂ per hour", "Bus kg CO₂ per hour", "Flight kg CO₂ per hour",
                  "Ferry kg CO₂ per hour"):
        assert label in box


def test_a_co2_price_reranks_and_shows_the_breakdown_line(trip):  # noqa: F811
    client, trip_id = trip
    assert "CO₂ " not in client.get(f"/trips/{trip_id}").text.split("<legend>CO₂</legend>")[0].split('id="table"')[-1]
    r = client.get(f"/trips/{trip_id}", params={"co2_price_kg": "1", "co2_train_kg_h": "10"})
    assert r.status_code == 200
    assert re.search(r"CO₂ \d+ kg", r.text)


def test_a_negative_or_too_high_value_is_a_form_error(trip):  # noqa: F811
    client, trip_id = trip
    assert client.get(f"/trips/{trip_id}", params={"co2_price_kg": "-1"}).status_code == 422
    assert client.get(f"/trips/{trip_id}", params={"co2_price_kg": "11"}).status_code == 422
    assert client.get(f"/trips/{trip_id}", params={"co2_bus_kg_h": "-0.1"}).status_code == 422
    token = csrf(client, trip_id)
    r = client.post("/profiles", data={"csrf_token": token, "trip_id": trip_id, "name": "X", "co2_price_kg": "-1"})
    assert r.status_code == 422


def test_save_as_profile_and_the_profile_page_keep_the_five_values(trip, sessions):  # noqa: F811
    client, trip_id = trip
    token = csrf(client, trip_id)
    client.post("/profiles", data={"csrf_token": token, "trip_id": trip_id, "name": "Green", **FIELDS})
    with sessions() as s:
        profile = s.query(ScoreProfile).one()
        pid, weights = profile.id, from_config(profile.config_json)
    for name, value in FIELDS.items():
        assert str(getattr(weights, name)) == value
    box = _fieldset(client.get(f"/profiles/{pid}").text)
    for name, value in FIELDS.items():
        assert re.search(rf'name="{name}"[^>]*value="{re.escape(value)}"', box), name
    r = client.post(f"/profiles/{pid}", data={"csrf_token": token, "name": "Green", **FIELDS, "co2_price_kg": "-2"})
    assert r.status_code == 422 and "co2_price_kg" in r.text
