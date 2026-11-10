"""The transfer place markups in the settings export and import (#1849, #1852): the slots come back the same."""

import json
import re
from decimal import Decimal

from app.models import ScoreProfile
from app.profiles import from_config, to_config
from app.ranking import Weights
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture: a logged-in client and an empty trip)


def _weights():
    return Weights(transfer_place1_name="Brussels-Midi", transfer_place1_markup=Decimal("20"),
                   transfer_place2_name="Lille", transfer_place2_markup=Decimal("-4"))


def _csrf(client, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _only_profile(sessions, config):
    """The database has no profile but one with `config`."""
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.add(ScoreProfile(name="Transfers", is_default=True, config_json=config))
        s.commit()


def _file(export, config):
    """A settings file with the profile `config` only."""
    return json.dumps({"format": export["format"], "version": export["version"],
                       "profiles": [{"name": "Transfers", "is_default": True, "config": config}],
                       "places": [], "rates": [], "fees": [], "settings": {}})


def test_the_export_has_the_transfer_place_slots(trip, sessions):  # noqa: F811
    client, _, _ = trip
    _only_profile(sessions, to_config(_weights()))
    config = client.get("/settings/export.json").json()["profiles"][0]["config"]
    assert config["transfer_place1_name"] == "Brussels-Midi" and config["transfer_place1_markup"] == "20"
    assert config["transfer_place2_name"] == "Lille" and config["transfer_place2_markup"] == "-4"


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


def test_a_bad_transfer_place_markup_in_the_file_imports_no_profile(trip, sessions):  # noqa: F811
    client, _, _ = trip
    _only_profile(sessions, to_config(_weights()))
    export = client.get("/settings/export.json").json()
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.commit()
    bad = dict(export["profiles"][0]["config"], transfer_place1_markup="abc")
    r = client.post("/settings/import", data={"csrf_token": _csrf(client, "/settings/import")},
                    files={"file": ("settings.json", _file(export, bad), "application/json")})
    assert r.status_code == 400 and "transfer_place1_markup" in r.text
    with sessions() as s:
        assert s.query(ScoreProfile).count() == 0
