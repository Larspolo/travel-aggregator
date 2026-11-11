"""The bicycle transport of an ÖBB fare (#2460, epic #2456): bikeAccessible true is "allowed", false "no", else None."""

import copy
import json
from pathlib import Path

from app.parsers.oebb import OebbParser

FIX = Path(__file__).parent / "fixtures" / "oebbtickets.at"


def _raw():
    return json.loads((FIX / "fares-amsterdam-wien-nightjet.json").read_text(encoding="utf-8"))


def test_the_nightjet_fares_allow_the_bicycle():
    r = OebbParser().parse(_raw())
    assert r.errors == []
    assert [o.bike for o in r.offers] == ["allowed", "allowed", "allowed"]


def test_a_connection_that_refuses_the_bicycle_gives_no():
    raw = copy.deepcopy(_raw())
    raw["connection"]["bikeAccessible"] = False
    assert [o.bike for o in OebbParser().parse(raw).offers] == ["no", "no", "no"]


def test_a_connection_with_no_bike_key_gives_none():
    raw = copy.deepcopy(_raw())
    del raw["connection"]["bikeAccessible"]
    assert [o.bike for o in OebbParser().parse(raw).offers] == [None, None, None]


def test_a_bike_value_that_is_not_a_boolean_gives_none():
    raw = copy.deepcopy(_raw())
    raw["connection"]["bikeAccessible"] = "yes"
    assert [o.bike for o in OebbParser().parse(raw).offers] == [None, None, None]
