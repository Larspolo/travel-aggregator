"""The on-board services of a train leg (#2549): bahn.de reads the zugattribute keys WV (wifi) and LS (power),
SNCF Connect reads the onBoardServices code WIFI; other codes are dropped, and a leg with no attribute has no services."""

import copy
import json
from pathlib import Path

from app.parsers.bahn import BahnParser
from app.parsers.sncf import SncfParser

BAHN = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-amsterdam-zuerich.json"
SNCF = Path(__file__).parent / "fixtures" / "sncf-connect.com" / "search-paris-lyon.json"


def bahn_legs(raw):
    return [leg for o in BahnParser().parse(raw).offers for leg in o.legs]


def ice_105(raw):
    return [leg for leg in bahn_legs(raw) if leg.service_no == "ICE 105"]


def fixture(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_bahn_ice_leg_has_wifi_and_power_when_the_leg_says_so():
    raw = fixture(BAHN)
    # the fixture's ICE 105 says wifi (WV) only: add the power sockets (LS) to it, as the real leg may say
    for conn in raw["response"]["verbindungen"]:
        for a in conn["verbindungsAbschnitte"]:
            if a["verkehrsmittel"].get("name") == "ICE 105":
                a["verkehrsmittel"]["zugattribute"].append({"kategorie": "INFORMATION", "key": "LS", "value": "power"})
    legs = ice_105(raw)
    assert legs and all(leg.services == ["wifi", "power"] for leg in legs)


def test_bahn_fixture_gives_the_services_the_legs_say():
    raw = fixture(BAHN)
    assert {tuple(leg.services) for leg in ice_105(raw)} == {("wifi",)}
    regional = [leg for leg in bahn_legs(raw) if leg.service_no == "20073"]
    assert regional and all(leg.services == ["power"] for leg in regional)


def test_bahn_leg_with_no_zugattribute_has_no_services():
    raw = copy.deepcopy(fixture(BAHN))
    for conn in raw["response"]["verbindungen"]:
        for a in conn["verbindungsAbschnitte"]:
            if a["verkehrsmittel"].get("name") == "ICE 105":
                del a["verkehrsmittel"]["zugattribute"]
    legs = ice_105(raw)
    assert legs and all(leg.services == [] for leg in legs)


def test_sncf_fixture_gives_wifi_for_a_leg_with_wifi():
    r = SncfParser().parse(fixture(SNCF))
    legs = [leg for o in r.offers for leg in o.legs]
    assert any(leg.services == ["wifi"] for leg in legs)


def test_sncf_drops_codes_other_than_wifi():
    raw = copy.deepcopy(fixture(SNCF))
    for prop in raw["response"]["longDistance"]["proposals"]["proposals"]:
        for step in prop["globalTimeline"]["steps"]:
            if step.get("train"):
                step["train"]["onBoardServices"] = [{"code": "VELO_GRATUIT"}, {"code": "VOITURE_BAR"}]
    legs = [leg for o in SncfParser().parse(raw).offers for leg in o.legs]
    assert legs and all(leg.services == [] for leg in legs)


def test_parser_versions_are_bumped():
    assert BahnParser.version == "1.4.0"
    assert SncfParser.version == "1.1.0"
