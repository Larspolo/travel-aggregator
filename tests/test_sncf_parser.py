"""The SNCF Connect search parser (#981) with the fixtures of tests/fixtures/sncf-connect.com."""

import copy
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers import all_sources, get_parser
from app.parsers.sncf import SncfParser, price
from app.search_links import links_by_source

FIX = Path(__file__).parent / "fixtures" / "sncf-connect.com"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["search-paris-lyon.json", "search-paris-marseille.json"])
def test_all_fixtures_give_offers(name):
    r = SncfParser().parse(load(name))
    assert r.offers and r.errors == []
    for o in r.offers:
        assert isinstance(o.price_amount, Decimal)
        assert o.price_currency == "EUR"
        assert o.travel_class in ("first", "standard")
        for leg in o.legs:
            assert leg.mode == "train"
            assert leg.depart_at.utcoffset() == timedelta(hours=1)
            assert leg.depart_at.date().isoformat() == "2026-12-01"
            assert leg.arrive_at > leg.depart_at


def test_first_tgv_has_four_fares():
    r = SncfParser().parse(load("search-paris-lyon.json"))
    first = [o for o in r.offers if o.external_id == r.offers[0].external_id]
    assert [o.price_amount for o in first] == [Decimal(55), Decimal(160), Decimal(180), Decimal(47)]
    assert [o.travel_class for o in first] == ["first"] * 3 + ["standard"]
    leg = first[0].legs[0]
    assert (leg.carrier, leg.service_no, leg.to_name) == ("TGV INOUI", "6641", "Lyon Part Dieu")
    assert (leg.depart_at.hour, leg.depart_at.minute) == (6, 20)
    assert first[0].fare_name == "Tarif STANDARD PREMIÈRE"


def test_price_label():
    assert price("25,50 €") == Decimal("25.50")
    assert price("55 €") == Decimal("55.00")
    assert price("65,6 €") == Decimal("65.60")
    with pytest.raises(ValueError):
        price("55 $")


def test_connection_and_ouigo():
    r = SncfParser().parse(load("search-paris-marseille.json"))
    conn = [o for o in r.offers if len(o.legs) == 2]
    assert conn
    assert conn[0].legs[0].to_name == conn[0].legs[1].from_name == "Lyon Part Dieu"
    ouigo = [o for o in r.offers if o.legs[0].carrier == "OUIGO"]
    assert [o.price_amount for o in ouigo] == [Decimal(25), Decimal(16)]
    assert len({o.external_id for o in ouigo}) == 1


def test_next_day_arrival():
    raw = copy.deepcopy(load("search-paris-lyon.json"))
    step = [s for s in raw["response"]["longDistance"]["proposals"]["proposals"][0]["globalTimeline"]["steps"]
            if "train" in s][0]["train"]
    step["departure"]["timeLabel"], step["arrival"]["timeLabel"] = "23:30", "01:10"
    leg = SncfParser().parse(raw).offers[0].legs[0]
    assert leg.arrive_at - leg.depart_at == timedelta(hours=1, minutes=40)


def test_broken_proposal_is_rejected_and_others_stay():
    raw = copy.deepcopy(load("search-paris-lyon.json"))
    props = raw["response"]["longDistance"]["proposals"]["proposals"]
    del props[1]["globalTimeline"]
    props[2]["status"]["isBookable"] = False
    r = SncfParser().parse(raw)
    assert [e["index"] for e in r.errors] == [1]
    assert {o.external_id for o in r.offers} == {props[0]["travelId"]}


def test_response_only_and_registry():
    raw = load("search-paris-lyon.json")["response"]
    assert get_parser("sncf-connect.com").parse(raw).offers
    assert "sncf-connect.com" in all_sources()
    assert links_by_source(None)["sncf-connect.com"][0] == "SNCF Connect"
    with pytest.raises(ValueError):
        SncfParser().parse({"longDistance": {}})
