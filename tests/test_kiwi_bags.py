"""The checked bags of a Kiwi.com fare from `bagsInfo` (#1526)."""

import copy
import json
from decimal import Decimal
from pathlib import Path

from app.parsers.kiwi import KiwiParser

FIX = Path(__file__).parent / "fixtures" / "kiwi.com"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_fixture_gives_included_bags_and_lowest_tier_price():
    r = KiwiParser().parse(load("search-amsterdam-zurich.json"))
    assert r.errors == []
    first = r.offers[0]
    assert first.checked_bags_included == 0
    assert first.checked_bag_price == Decimal("25.06")


def _first_itinerary(raw):
    return raw["response"]["data"]["onewayItineraries"]["itineraries"][0]


def test_included_bag_count_is_read():
    raw = load("search-amsterdam-zurich.json")
    it = _first_itinerary(raw)
    it["bagsInfo"]["includedCheckedBags"] = 1
    r = KiwiParser().parse(raw)
    assert r.offers[0].checked_bags_included == 1


def test_missing_bags_info_gives_none():
    raw = load("search-amsterdam-zurich.json")
    del _first_itinerary(raw)["bagsInfo"]
    r = KiwiParser().parse(raw)
    assert r.errors == []
    assert r.offers[0].checked_bags_included is None
    assert r.offers[0].checked_bag_price is None


def test_bad_tier_price_is_skipped():
    raw = copy.deepcopy(load("search-amsterdam-zurich.json"))
    tiers = _first_itinerary(raw)["bagsInfo"]["checkedBagTiers"]
    tiers[0]["tierPrice"]["amount"] = "not a number"
    r = KiwiParser().parse(raw)
    assert r.offers[0].checked_bag_price == Decimal("81.39")
