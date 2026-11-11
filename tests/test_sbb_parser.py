"""The SBB connection search parser (#1786) with the fixtures of tests/fixtures/sbb.ch."""

import copy
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers import get_parser, parser_classes
from app.parsers.sbb import SbbParser

FIX = Path(__file__).parent / "fixtures" / "sbb.ch"
HALF = "search-basel-zuerich-half-fare.json"
FULL = "search-basel-zuerich.json"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def at(offers, hhmm):
    return [o for o in offers if o.legs[0].depart_at.strftime("%H:%M") == hhmm]


@pytest.mark.parametrize("name,trips", [(HALF, 4), (FULL, 5)])
def test_all_fixtures_give_offers(name, trips):
    r = SbbParser().parse(load(name))
    assert r.errors == []
    assert len({o.external_id for o in r.offers}) == trips
    assert len(r.offers) == 2 * trips  # one 2nd and one 1st class price per trip
    assert r.travelers == 1
    for o in r.offers:
        assert isinstance(o.price_amount, Decimal) and o.price_currency == "CHF"
        assert o.travel_class in ("first", "standard")
        for leg in o.legs:
            assert leg.mode == "train" and leg.service_no
            assert leg.depart_at.utcoffset().total_seconds() == 3600


def test_direct_ic_with_half_fare_prices():
    r = SbbParser().parse(load(HALF))
    assert r.discounts == ["Half Fare card"]
    offers = {o.travel_class: o for o in at(r.offers, "07:33")}
    o = offers["standard"]
    assert len(o.legs) == 1 and o.legs[0].service_no == "IC 561"
    assert (o.legs[0].from_name, o.legs[0].to_name) == ("Basel SBB", "Zürich HB")
    assert o.legs[0].arrive_at.strftime("%H:%M") == "08:26"
    assert o.price_amount == Decimal("18.00") and o.fare_name == "Saver, 2nd class"
    assert offers["first"].price_amount == Decimal("31.00")


def test_transfer_and_no_card():
    r = SbbParser().parse(load(FULL))
    assert r.discounts == []
    two = [o for o in at(r.offers, "08:43") if len(o.legs) == 2]
    assert [x.service_no for x in two[0].legs] == ["IR 2263", "IC 513"]
    assert two[0].legs[0].to_name == two[0].legs[1].from_name
    second = next(o for o in two if o.travel_class == "standard")
    assert second.price_amount == Decimal("21.40") and second.fare_name == "Flex, 2nd class"


def test_trip_with_no_price_is_rejected_and_others_stay():
    raw = copy.deepcopy(load(HALF))
    del raw["prices"]["response"]["data"]["tripPrices"][0]
    r = SbbParser().parse(raw)
    assert [e["index"] for e in r.errors] == [0] and "no price" in r.errors[0]["reason"]
    assert len({o.external_id for o in r.offers}) == 3


def test_broken_trip_is_rejected():
    raw = copy.deepcopy(load(FULL))
    del raw["response"]["data"]["trips"]["trips"][1]["legs"][0]["departure"]
    r = SbbParser().parse(raw)
    assert [e["index"] for e in r.errors] == [1]
    assert len({o.external_id for o in r.offers}) == 4


@pytest.mark.parametrize("raw", [[], {"data": {}}, {"response": {"data": {"trips": {"trips": []}}}}])
def test_other_form_or_no_connections_fails_with_a_reason(raw):
    with pytest.raises(ValueError, match="sbb.ch"):
        SbbParser().parse(raw)


def test_registry_and_no_har_rule_before_the_userscript():
    assert isinstance(get_parser("sbb.ch"), SbbParser)
    cls = parser_classes()["sbb.ch"]
    assert cls.hosts == () and cls.paths == ()


@pytest.mark.parametrize("name", [HALF, FULL])
def test_fixture_has_no_personal_data(name):
    text = (FIX / name).read_text(encoding="utf-8").lower()
    for word in ("cookie", "token", "authorization", "email", "e-mail", "firstname", "lastname", "birth"):
        assert word not in text
    assert not re.search(r"[\w.]+@[\w.]+", text)
