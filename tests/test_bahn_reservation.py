"""The mandatory seat reservation of each bahn.de leg (#1621): RP and GP in the zugattribute of the leg."""

import copy
import json
from pathlib import Path

from app.parsers.bahn import BahnParser

FIX = Path(__file__).parent / "fixtures" / "bahn.de"


def load(name):
    raw = json.loads((FIX / name).read_text(encoding="utf-8"))
    return raw.get("response", raw)


def first_leg(conn):
    """The reservation of the first leg of the connection, as the parser gives it."""
    r = BahnParser().parse({"verbindungen": [conn]})
    assert len(r.offers) >= 1
    return r.offers[0].legs[0].reservation


def test_nj_403_with_global_price_is_included():
    conn = load("fahrplan-amsterdam-bern-night.json")["verbindungen"][0]
    assert first_leg(conn) == "included"


def test_ice_141_with_recommendation_only_is_none():
    conn = load("fahrplan-amsterdam-berlin.json")["verbindungen"][0]
    assert first_leg(conn) is None


def test_gv_327_without_global_price_is_required():
    conn = copy.deepcopy(load("fahrplan-amsterdam-berlin.json")["verbindungen"][3])
    assert conn["verbindungsAbschnitte"][0]["verkehrsmittel"]["name"] == "GV 327"
    # the fixture has no price: give the connection one, so that the parser makes an offer
    conn["angebotsPreis"] = {"betrag": 39.99, "waehrung": "EUR"}
    assert first_leg(conn) == "required"


def test_parser_version_is_1_3_0():
    assert BahnParser.version == "1.3.0"
