"""The carrier markups in the settings export and import (#1530, epic #1529): the slots come back the same."""

import json
import re
from decimal import Decimal

from app.models import ScoreProfile
from app.profiles import from_config, to_config
from app.ranking import Weights
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture: a logged-in client and an empty trip)


def _weights():
    return Weights(carrier1_name="Ryanair", carrier1_markup=Decimal("15"),
                   carrier2_name="KLM", carrier2_markup=Decimal("-5"))


def _csrf(client, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _only_profile(sessions, config):
    """The database has no profile but one with `config`."""
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.add(ScoreProfile(name="Carriers", is_default=True, config_json=config))
        s.commit()


def _file(export, config):
    """A settings file with the profile `config` only."""
    return json.dumps({"format": export["format"], "version": export["version"],
                       "profiles": [{"name": "Carriers", "is_default": True, "config": config}],
                       "places": [], "rates": [], "fees": [], "settings": {}})


def test_the_export_has_the_carrier_slots(trip, sessions):  # noqa: F811
    client, _, _ = trip
    _only_profile(sessions, to_config(_weights()))
    config = client.get("/settings/export.json").json()["profiles"][0]["config"]
    assert config["carrier1_name"] == "Ryanair" and config["carrier1_markup"] == "15"
    assert config["carrier2_name"] == "KLM" and config["carrier2_markup"] == "-5"


def test_the_import_gives_the_same_weights(trip, sessions):  # noqa: F811
    client, _, _ = trip
    _only_profile(sessions, to_config(_weights()))
    export = client.get("/settings/export.json").json()
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.commit()
    r = client.post("/settings/import", data={"csrf_token": _csrf(client, "/settings/import")},
                    files={"file": ("settings.json", _file(export, export["profiles"][0]["config"]),
                                    "application/json")})
    assert r.status_code == 200 and "imported" in r.text
    with sessions() as s:
        rows = s.query(ScoreProfile).all()
        assert len(rows) == 1 and from_config(rows[0].config_json) == _weights()


def test_a_bad_carrier_markup_in_the_file_imports_no_profile(trip, sessions):  # noqa: F811
    client, _, _ = trip
    _only_profile(sessions, to_config(_weights()))
    export = client.get("/settings/export.json").json()
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.commit()
    bad = dict(export["profiles"][0]["config"], carrier1_markup="abc")
    r = client.post("/settings/import", data={"csrf_token": _csrf(client, "/settings/import")},
                    files={"file": ("settings.json", _file(export, bad), "application/json")})
    assert r.status_code == 400 and "carrier1_markup" in r.text
    with sessions() as s:
        assert s.query(ScoreProfile).count() == 0
