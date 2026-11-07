"""The NS service number is the category and the number, as on bahn.de ("ICE 121"), and the category is no carrier (#483)."""

import json
from pathlib import Path

from app.parsers.ns import NsParser, _service_no

FIX = Path(__file__).parent / "fixtures" / "nsinternational.com"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_first_leg_of_first_offer_is_ice_121_without_carrier():
    leg = NsParser().parse(load("search-amsterdam-berlin.json")).offers[0].legs[0]
    assert (leg.service_no, leg.carrier) == ("ICE 121", None)


def test_number_alone_without_category():
    assert _service_no({"number": "545"}) == "545"


def test_no_number_gives_none():
    assert _service_no({"code": "ICE", "name": "ICE"}) is None
    assert _service_no({"code": "ICE", "name": "ICE", "number": "  "}) is None
