"""The NS International search parser (#212) with the fixtures of tests/fixtures/nsinternational.com."""

import copy
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.ingest import fingerprint
from app.parsers import get_parser
from app.parsers.ns import NsParser

FIX = Path(__file__).parent / "fixtures" / "nsinternational.com"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,offers", [
    ("search-amsterdam-london.json", 10),
    ("search-amsterdam-berlin.json", 18),
    ("search-rotterdam-paris.json", 9),
])
def test_all_fixtures_give_offers(name, offers):
    r = NsParser().parse(load(name))
    assert len(r.offers) == offers
    assert r.errors == []
    for o in r.offers:
        assert isinstance(o.price_amount, Decimal)
        assert o.price_currency == "EUR"
        assert o.fare_name and not o.fare_name.startswith(" ")
        for leg in o.legs:
            assert leg.depart_at.tzinfo is not None


def test_direct_eurostar_times_offsets_price():
    o = NsParser().parse(load("search-amsterdam-london.json")).offers[0]
    assert (o.fare_name, o.price_amount) == ("Standard Premier, semi-flexible", Decimal("155.00"))
    assert len(o.legs) == 1
    leg = o.legs[0]
    assert (leg.carrier, leg.from_code, leg.to_code) == (None, "NLASC", "GBSPX")
    assert leg.depart_at.utcoffset() == timedelta(hours=1)
    assert leg.arrive_at.utcoffset() == timedelta(0)
    assert leg.depart_at.hour == 6 and leg.arrive_at.hour == 9


def test_changes_give_train_legs_without_transfer():
    r = NsParser().parse(load("search-amsterdam-london.json"))
    legs = [o for o in r.offers if o.external_id.startswith("0911974b")][0].legs
    assert [leg.service_no for leg in legs] == ["SPR 8227", "Eurocity Direct 9520", "Eurostar 9123"]
    assert legs[-1].to_code == "GBSPX"


def test_two_offers_are_two_fares_of_one_itinerary():
    r = NsParser().parse(load("search-amsterdam-berlin.json"))
    first = [o for o in r.offers if o.external_id == r.offers[0].external_id]
    assert len(first) == 6
    assert len({fingerprint(o.legs) for o in first}) == 1
    assert len({o.fare_name for o in first}) == 6


def test_missing_field_is_rejected_and_others_stay():
    raw = copy.deepcopy(load("search-rotterdam-paris.json"))
    del raw["response"]["data"]["travelOffers"][1]["itinerary"]["origin"]["departure"]
    r = NsParser().parse(raw)
    assert len(r.offers) == 6
    assert [e["index"] for e in r.errors] == [1]


def test_response_only_and_registry():
    raw = load("search-rotterdam-paris.json")["response"]
    assert len(get_parser("nsinternational.com").parse(raw).offers) == 9
    with pytest.raises(ValueError):
        NsParser().parse({"data": {}})
