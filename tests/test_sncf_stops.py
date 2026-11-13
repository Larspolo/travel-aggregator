"""The stops between the ends of a train leg of SNCF Connect (#2716): the fixture of tests/fixtures/sncf-connect.com
gives the stops of each train, and a small payload gives the cases."""

import json
from pathlib import Path

from app.parsers.sncf import SncfParser
from app.schemas import StopIn

FIX = Path(__file__).parent / "fixtures" / "sncf-connect.com"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def legs_by_train(result):
    """The legs of the first offer of each train, by the service number (the train of the proposal)."""
    out = {}
    for offer in result.offers:
        for leg in offer.legs:
            out.setdefault(leg.service_no, leg)
    return out


def test_fixture_stops_of_tgv_6641():
    r = SncfParser().parse(load("search-paris-lyon.json"))
    leg = legs_by_train(r)["6641"]
    assert len(leg.stops) == 1
    assert leg.stops[0].name == "Le Creusot - Montceau-Les-Mines - Montchanin TGV"
    assert leg.stops[0].code == "8769410"


def test_fixture_stops_of_train_17769():
    r = SncfParser().parse(load("search-paris-lyon.json"))
    leg = legs_by_train(r)["17769"]
    assert len(leg.stops) == 17
    assert leg.stops[0].name == "Sens"
    assert leg.stops[0].code == "8768300"
    assert leg.stops[-1].name == "Saint-Germain-Au-Mont-d'Or"


def test_fixture_tgv_6603_has_no_stops():
    r = SncfParser().parse(load("search-paris-lyon.json"))
    assert legs_by_train(r)["6603"].stops == []


def test_stop_codes_and_skipped_items():
    raw = load("search-paris-lyon.json")
    train = _first_train(raw, "6641")
    train["stops"] = [
        {"location": {"label": "", "labelComplement": "RESARAIL_STA_1"}},
        {"location": {"labelComplement": "RESARAIL_STA_2"}},
        {"location": {"label": "Dijon", "labelComplement": "no id here"}},
        {"location": {"label": "Mâcon", "labelComplement": "RESARAIL_STA_42"}},
    ]
    leg = SncfParser().parse(raw).offers[0].legs[0]
    assert leg.stops == [StopIn(name="Dijon", code=None), StopIn(name="Mâcon", code="42")]


def test_train_without_stops_key_gives_none():
    raw = load("search-paris-lyon.json")
    del _first_train(raw, "6641")["stops"]
    leg = SncfParser().parse(raw).offers[0].legs[0]
    assert leg.stops is None


def test_train_with_empty_stops_gives_empty_list():
    raw = load("search-paris-lyon.json")
    _first_train(raw, "6641")["stops"] = []
    leg = SncfParser().parse(raw).offers[0].legs[0]
    assert leg.stops == []


def test_parser_version_is_1_2_0():
    assert SncfParser.version == "1.2.0"


def _first_train(raw, number):
    """The train step with this service number, in the raw payload (a copy is not needed: the caller loads it)."""
    for prop in raw["response"]["longDistance"]["proposals"]["proposals"]:
        for step in prop["globalTimeline"]["steps"]:
            t = step.get("train")
            if t and t["transporter"].get("number", "").replace("n°", "").strip() == number:
                return t
    raise AssertionError(f"no train {number}")
