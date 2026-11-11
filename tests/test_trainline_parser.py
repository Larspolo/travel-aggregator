"""The Trainline journey search parser (#977) with the fixtures of tests/fixtures/thetrainline.com."""

import copy
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers import get_parser
from app.parsers.trainline import TrainlineParser

FIX = Path(__file__).parent / "fixtures" / "thetrainline.com"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def by_depart(offers, hhmm):
    return [o for o in offers if o.legs[0].depart_at.strftime("%H:%M") == hhmm]


@pytest.mark.parametrize("name", ["search-london-edinburgh.json", "search-amsterdam-berlin.json"])
def test_all_fixtures_give_offers(name):
    r = TrainlineParser().parse(load(name))
    assert r.errors == []
    assert len({o.external_id for o in r.offers}) == 3
    assert r.travelers == 1
    for o in r.offers:
        assert isinstance(o.price_amount, Decimal)
        assert o.price_currency == "GBP"
        assert o.fare_name and o.travel_class in ("first", "standard")
        for leg in o.legs:
            assert leg.mode == "train" and leg.carrier
            assert leg.depart_at.tzinfo is not None and leg.arrive_at.tzinfo is not None


def test_london_transfer_at_york():
    offers = by_depart(TrainlineParser().parse(load("search-london-edinburgh.json")).offers, "10:33")
    o = offers[0]
    assert len(o.legs) == 2
    assert "York" in o.legs[0].to_name and o.legs[0].to_name == o.legs[1].from_name
    assert o.legs[0].service_no is None
    assert o.legs[0].depart_at.utcoffset().total_seconds() == 0


def test_amsterdam_direct_ice():
    offers = by_depart(TrainlineParser().parse(load("search-amsterdam-berlin.json")).offers, "10:00")
    assert len(offers) == 6
    o = offers[0]
    assert len(o.legs) == 1 and o.legs[0].service_no == "ICE 145"
    assert o.legs[0].depart_at.utcoffset().total_seconds() == 3600
    names = {x.fare_name: x for x in offers}
    assert names["Sparpreis Europa, First"].travel_class == "first"
    assert names["Flexpreis Europa, Standard"].travel_class == "standard"


def test_one_fare_per_name_with_lowest_price():
    raw = load("search-london-edinburgh.json")
    r = TrainlineParser().parse(raw)
    for jid in {o.external_id for o in r.offers}:
        names = Counter(o.fare_name for o in r.offers if o.external_id == jid)
        assert max(names.values()) == 1
    js, ft = raw["response"]["data"]["journeySearch"], raw["response"]["data"]["fareTypes"]
    j = next(j for j in js["journeys"].values() if j["departAt"].startswith("2026-12-01T10:03"))
    prices = [
        Decimal(str(a["price"]["amount"]))
        for s in j["sections"] for a in (js["alternatives"][x] for x in js["sections"][s]["alternatives"])
        if ft[js["fares"][a["fares"][0]]["fareType"]]["name"] == "Advance Single"
    ]
    o = next(o for o in r.offers if o.external_id == j["id"] and o.fare_name == "Advance Single, Standard")
    assert o.price_amount == min(prices)
    assert "Advance Single (1st Class)" in {x.fare_name for x in r.offers}


def test_partial_alternative_is_skipped():
    raw = copy.deepcopy(load("search-amsterdam-berlin.json"))
    for a in raw["response"]["data"]["journeySearch"]["alternatives"].values():
        a["isPartial"] = True
    assert TrainlineParser().parse(raw).offers == []


def test_broken_journey_is_rejected_and_others_stay():
    raw = copy.deepcopy(load("search-amsterdam-berlin.json"))
    js = raw["response"]["data"]["journeySearch"]
    first = next(iter(js["journeys"].values()))
    del js["legs"][first["legs"][0]]["departAt"]
    r = TrainlineParser().parse(raw)
    assert [e["index"] for e in r.errors] == [0]
    assert len({o.external_id for o in r.offers}) == 2


def test_response_only_and_registry():
    raw = load("search-amsterdam-berlin.json")["response"]
    assert get_parser("thetrainline.com").parse(raw).offers
    with pytest.raises(ValueError):
        TrainlineParser().parse({"data": {}})
