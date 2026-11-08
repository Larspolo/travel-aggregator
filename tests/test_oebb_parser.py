"""The ÖBB parser (#951) with the fixtures of tests/fixtures/oebbtickets.at."""

import copy
import json
from decimal import Decimal
from pathlib import Path

from app.parsers import get_parser
from app.parsers.oebb import OebbParser

FIX = Path(__file__).parent / "fixtures" / "oebbtickets.at"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def priced(name, amount=Decimal("49.90")):
    """A capture of a search response with a price for each connection."""
    body = load(name)
    return {"response": body, "prices": {c["id"]: str(amount) for c in body["connections"]}}


def test_nightjet_gives_one_fare_per_tier_and_arrives_next_day():
    r = OebbParser().parse(load("fares-amsterdam-wien-nightjet.json"))
    assert r.errors == []
    assert [o.fare_name for o in r.offers] == ["Seat", "Couchette", "Sleeper"]
    # the cheapest tier price of the Nightjet plus the cheapest 2nd class RJX fare (24.90)
    assert [o.price_amount for o in r.offers] == [Decimal("59.80"), Decimal("124.80"), Decimal("204.80")]
    assert len({tuple((leg.service_no, leg.depart_at) for leg in o.legs) for o in r.offers}) == 1
    nj, rjx = r.offers[0].legs
    assert (nj.mode, nj.service_no, rjx.service_no) == ("train", "NJ 40421", "RJX 19969")
    assert nj.depart_at.isoformat() == "2026-12-01T18:01:00+01:00"
    assert rjx.arrive_at.isoformat() == "2026-12-02T09:32:00+01:00"
    assert (rjx.arrive_at.date() - nj.depart_at.date()).days == 1


def test_search_fixtures_give_offers_with_legs_and_offsets():
    for name, n in (("search-amsterdam-wien.json", 2), ("search-wien-zuerich.json", 2)):
        r = OebbParser().parse(priced(name))
        assert r.errors == [] and len(r.offers) == n
        for o, conn in zip(r.offers, load(name)["connections"]):
            assert o.price_amount == Decimal("49.90") and o.price_currency == "EUR"
            assert len(o.legs) == conn["switches"] + 1 and o.legs[0].depart_at.utcoffset() is not None
            assert o.legs[0].depart_at.replace(tzinfo=None).isoformat() == conn["from"]["departure"][:19]


def test_zurich_has_the_swiss_offset():
    r = OebbParser().parse(priced("search-wien-zuerich.json"))
    last = r.offers[0].legs[-1]
    assert last.to_name.startswith("Z") and last.arrive_at.utcoffset().total_seconds() == 3600


def test_broken_connection_is_rejected_and_others_stay():
    raw = priced("search-amsterdam-wien.json")
    raw["response"] = copy.deepcopy(raw["response"])
    del raw["response"]["connections"][0]["sections"][0]["from"]["departure"]
    r = OebbParser().parse(raw)
    assert len(r.offers) == 1 and [e["index"] for e in r.errors] == [0]
    assert "departure" in r.errors[0]["reason"]


def test_search_with_no_price_is_rejected():
    r = OebbParser().parse(load("search-amsterdam-wien.json"))
    assert r.offers == [] and [e["reason"] for e in r.errors] == ["bad connection: ValueError no price"] * 2


def test_registry():
    assert isinstance(get_parser("oebbtickets.at"), OebbParser)
