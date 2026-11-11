"""The weekday markups in the settings export and import (#2137, pattern #1530): the 7 slots come back the same."""

import json
import re
from decimal import Decimal

from app.models import ScoreProfile
from app.profiles import from_config, to_config
from app.ranking import Weights
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture: a logged-in client and an empty trip)


def _weights():
    # ISO weekdays: 5 = Friday, 7 = Sunday (#2136).
    return Weights(weekday5_markup=Decimal("15"), weekday7_markup=Decimal("-5"))


def _csrf(client, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _only_profile(sessions, config):
    """The database has no profile but one with `config`."""
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.add(ScoreProfile(name="Weekdays", is_default=True, config_json=config))
        s.commit()


def _file(export, config):
    """A settings file with the profile `config` only."""
    return json.dumps({"format": export["format"], "version": export["version"],
                       "profiles": [{"name": "Weekdays", "is_default": True, "config": config}],
                       "places": [], "rates": [], "fees": [], "settings": {}})


def test_the_export_has_the_weekday_slots(trip, sessions):  # noqa: F811
    client, _, _ = trip
    _only_profile(sessions, to_config(_weights()))
    config = client.get("/settings/export.json").json()["profiles"][0]["config"]
    assert config["weekday5_markup"] == "15" and config["weekday7_markup"] == "-5"
    for day in (1, 2, 3, 4, 6):
        assert config[f"weekday{day}_markup"] == "0"


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
