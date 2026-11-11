"""The carrier loyalty values in the settings export and import (#2434): the 3 values come back the same."""

import json
import re
from decimal import Decimal

from app.models import ScoreProfile
from app.profiles import from_config, to_config
from app.ranking import Weights
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture: a logged-in client and an empty trip)


def _weights():
    return Weights(carrier1_loyalty_pct=Decimal("5"), carrier2_loyalty_pct=Decimal("0"),
                   carrier3_loyalty_pct=Decimal("12"))


def _csrf(client, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _only_profile(sessions, config):
    """The database has no profile but one with `config`."""
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.add(ScoreProfile(name="Loyalty", is_default=True, config_json=config))
        s.commit()


def _file(export, config):
    """A settings file with the profile `config` only."""
    return json.dumps({"format": export["format"], "version": export["version"],
                       "profiles": [{"name": "Loyalty", "is_default": True, "config": config}],
                       "places": [], "rates": [], "fees": [], "settings": {}})


def _import(client, export, config):
    return client.post("/settings/import", data={"csrf_token": _csrf(client, "/settings/import")},
                       files={"file": ("settings.json", _file(export, config), "application/json")})


def test_the_export_and_import_keep_the_loyalty_value(trip, sessions):  # noqa: F811
    client, _, _ = trip
    _only_profile(sessions, to_config(_weights()))
    export = client.get("/settings/export.json").json()
    assert export["profiles"][0]["config"]["carrier1_loyalty_pct"] == "5"
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.commit()
    r = _import(client, export, export["profiles"][0]["config"])
    assert r.status_code == 200 and "imported" in r.text
    with sessions() as s:
        rows = s.query(ScoreProfile).all()
        assert len(rows) == 1 and from_config(rows[0].config_json).carrier1_loyalty_pct == Decimal("5")
        assert from_config(rows[0].config_json) == _weights()


def test_an_old_export_without_the_loyalty_key_imports_zero(trip, sessions):  # noqa: F811
    client, _, _ = trip
    _only_profile(sessions, to_config(_weights()))
    export = client.get("/settings/export.json").json()
    old = {k: v for k, v in export["profiles"][0]["config"].items() if k != "carrier1_loyalty_pct"}
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.commit()
    r = _import(client, export, old)
    assert r.status_code == 200 and "imported" in r.text
    with sessions() as s:
        rows = s.query(ScoreProfile).all()
        assert len(rows) == 1 and from_config(rows[0].config_json).carrier1_loyalty_pct == Decimal("0")
