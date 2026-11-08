"""The Eurostar journey search parser (#1018) with the fixtures of tests/fixtures/eurostar.com."""

import copy
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers import all_sources, get_parser
from app.parsers.eurostar import EurostarParser

FIX = Path(__file__).parent / "fixtures" / "eurostar.com"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"), parse_float=Decimal)


def by_depart(offers, hhmm):
    return [o for o in offers if o.legs[0].depart_at.strftime("%H:%M") == hhmm]


@pytest.mark.parametrize("name", ["search-amsterdam-london.json", "search-brussels-paris.json"])
def test_all_fixtures_give_offers(name):
    r = EurostarParser().parse(load(name))
    assert r.errors == []
    assert len({o.external_id for o in r.offers}) == 3
    assert r.travelers == 1
    for o in r.offers:
        assert isinstance(o.price_amount, Decimal) and o.price_currency == "GBP"
        assert o.fare_name.startswith("Eurostar ")
        assert o.travel_class in ("first", "standard")
        for leg in o.legs:
            assert leg.mode == "train" and leg.carrier == "Eurostar" and leg.service_no
            assert leg.depart_at.tzinfo is not None and leg.arrive_at.tzinfo is not None


def test_amsterdam_london_times_have_the_offset_of_each_station():
    offers = by_depart(EurostarParser().parse(load("search-amsterdam-london.json")).offers, "06:40")
    leg = offers[0].legs[0]
    assert leg.service_no == "9115"
    assert leg.depart_at.isoformat() == "2026-12-01T06:40:00+01:00"
    assert leg.arrive_at.isoformat() == "2026-12-01T09:57:00+00:00"
    assert leg.arrive_at - leg.depart_at == timedelta(minutes=257)
    assert {o.fare_name for o in offers} == {"Eurostar Standard", "Eurostar Plus", "Eurostar Premier"}
    tc = {o.fare_name: o.travel_class for o in offers}
    assert tc["Eurostar Premier"] == "first" and tc["Eurostar Plus"] == "standard"


def test_transfer_in_brussels():
    o = by_depart(EurostarParser().parse(load("search-amsterdam-london.json")).offers, "07:10")[0]
    assert [leg.service_no for leg in o.legs] == ["9316", "9123"]
    assert o.legs[0].to_name.startswith("Brussels") and o.legs[1].from_name.startswith("Brussels")
    assert o.legs[0].arrive_at.utcoffset() == timedelta(hours=1)


def test_same_times_other_trains_and_sold_out_fare():
    offers = EurostarParser().parse(load("search-brussels-paris.json")).offers
    at_0813 = by_depart(offers, "08:13")
    assert {o.legs[0].service_no for o in at_0813} == {"9410", "9310"}
    assert len({o.external_id for o in at_0813}) == 2
    late = by_depart(offers, "18:13")
    assert late and "Eurostar Premier" not in {o.fare_name for o in late}


def test_price_is_exact_decimal():
    raw = load("search-amsterdam-london.json")
    j = raw["response"]["data"]["journeySearch"]["outbound"]["journeys"][1]
    o = [x for x in EurostarParser().parse(raw).offers if x.legs[0].depart_at.strftime("%H:%M") == "07:10"]
    want = {f["classOfService"]["name"]: f["prices"]["displayPrice"] for f in j["fares"]}
    for x in o:
        assert x.price_amount == Decimal(str(want[x.fare_name])).quantize(Decimal("0.01"))


def test_text_payload_is_parsed():
    text = (FIX / "search-amsterdam-london.json").read_text(encoding="utf-8")
    assert len(EurostarParser().parse(text).offers) == len(EurostarParser().parse(load("search-amsterdam-london.json")).offers)


def test_a_broken_journey_is_rejected_and_the_others_stay():
    raw = copy.deepcopy(load("search-amsterdam-london.json"))
    journeys = raw["response"]["data"]["journeySearch"]["outbound"]["journeys"]
    del journeys[0]["fares"][0]["legs"][0]["timing"]
    r = EurostarParser().parse(raw)
    assert [e["index"] for e in r.errors] == [0]
    assert len({o.external_id for o in r.offers}) == 2


def test_no_journeys_is_an_error():
    with pytest.raises(ValueError):
        EurostarParser().parse({"response": {"data": {}}})


def test_registered():
    assert "eurostar.com" in all_sources()
    assert isinstance(get_parser("eurostar.com"), EurostarParser)
