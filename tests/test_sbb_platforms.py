"""The planned platforms of the SBB legs (#2733): `quayFormatted` of the departure and the arrival."""

import copy
import json
from pathlib import Path

from app.parsers.sbb import SbbParser

FIX = Path(__file__).parent / "fixtures" / "sbb.ch" / "search-basel-zuerich.json"


def raw_fixture():
    return json.loads(FIX.read_text(encoding="utf-8"))


def leg_named(raw, service_no):
    """The first leg of the parsed offers with this service number (the parser gives one offer per price)."""
    for offer in SbbParser().parse(raw).offers:
        for leg in offer.legs:
            if leg.service_no == service_no:
                return leg
    raise AssertionError(f"no leg {service_no}")


def test_ic_763_platform_9_to_9():
    leg = leg_named(raw_fixture(), "IC 763")
    assert leg.from_platform == "9"
    assert leg.to_platform == "9"


def test_ir_1963_platform_11_to_17():
    leg = leg_named(raw_fixture(), "IR 1963")
    assert leg.from_platform == "11"
    assert leg.to_platform == "17"


def test_ic_513_platform_3_to_33():
    leg = leg_named(raw_fixture(), "IC 513")
    assert leg.from_platform == "3"
    assert leg.to_platform == "33"


def test_null_or_missing_quay_gives_none():
    raw = copy.deepcopy(raw_fixture())
    trip = raw["response"]["data"]["trips"]["trips"][0]
    trip["legs"][0]["departure"]["quayFormatted"] = None
    del trip["legs"][0]["arrival"]["quayFormatted"]
    leg = leg_named(raw, "IC 763")
    assert leg.from_platform is None
    assert leg.to_platform is None


def test_a_platform_longer_than_ten_characters_gives_none():
    raw = copy.deepcopy(raw_fixture())
    raw["response"]["data"]["trips"]["trips"][0]["legs"][0]["departure"]["quayFormatted"] = "x" * 11
    assert leg_named(raw, "IC 763").from_platform is None
