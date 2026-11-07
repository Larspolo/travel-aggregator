"""The Flixbus search parser (#250) with the fixtures of tests/fixtures/flixbus.com."""

import copy
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers import get_parser
from app.parsers.flixbus import FlixbusParser

FIX = Path(__file__).parent / "fixtures" / "flixbus.com"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["search-amsterdam-paris.json", "search-amsterdam-berlin.json", "search-utrecht-berlin.json"])
def test_all_fixtures_give_offers(name):
    r = FlixbusParser().parse(load(name))
    assert len(r.offers) == 3
    assert r.errors == []
    for o in r.offers:
        assert isinstance(o.price_amount, Decimal)
        assert o.price_currency == "GBP"
        assert o.fare_name
        for leg in o.legs:
            assert leg.depart_at.utcoffset() == timedelta(hours=1)
            assert leg.arrive_at.tzinfo is not None


def test_direct_times_price_fare():
    o = FlixbusParser().parse(load("search-amsterdam-paris.json")).offers[0]
    assert (o.fare_name, o.price_amount) == ("Direct", Decimal("14.99"))
    assert len(o.legs) == 1
    assert o.legs[0].mode == "bus"
    assert o.legs[0].depart_at.hour == 0 and o.legs[0].depart_at.minute == 15


def test_transfer_gives_two_legs():
    r = FlixbusParser().parse(load("search-amsterdam-berlin.json"))
    o = [o for o in r.offers if o.fare_name == "Transfer"][0]
    assert [leg.mode for leg in o.legs] == ["bus", "train"]
    assert o.legs[0].to_name == o.legs[1].from_name
    assert o.price_amount == Decimal("25.48")


def test_missing_field_is_rejected_and_others_stay():
    raw = copy.deepcopy(load("search-amsterdam-paris.json"))
    conn = list(raw["response"]["trips"][1]["results"].values())[0]
    del conn["legs"][0]["departure"]
    r = FlixbusParser().parse(raw)
    assert len(r.offers) == 2
    assert [e["index"] for e in r.errors] == [1]


def test_response_only_and_registry():
    raw = load("search-amsterdam-paris.json")["response"]
    assert len(get_parser("flixbus.com").parse(raw).offers) == 3
    with pytest.raises(ValueError):
        FlixbusParser().parse({"stations": {}})
