"""The ÖBB parser with the prices responses of the page (#1050): GET /api/offer/v1/prices gives the price of each
connection of a search, and the userscript sends both in one capture."""

import json
from decimal import Decimal
from pathlib import Path

from app.parsers.oebb import OebbParser

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "oebbtickets.at"


def load(name):
    return json.loads((FIXTURES / name).read_text("utf-8"))


def capture(trip):
    """A capture as the userscript sends it: the timetable and the prices of its connections."""
    prices = {o["connectionId"]: str(o["price"]) for o in load(f"prices-{trip}.json")["offers"] if not o["offerError"]}
    return {"response": load(f"search-{trip}.json"), "prices": prices}


def parse(trip):
    r = OebbParser().parse(capture(trip))
    return r.offers, r.errors


def test_amsterdam_wien_gives_two_priced_offers():
    offers, errors = parse("amsterdam-wien")
    assert not errors
    ids = [c["id"][:8] for c in load("search-amsterdam-wien.json")["connections"]]
    # the offers come in the order of the connections: d6d32076... at 59.80, 9dfa4e9a... at 49.90
    assert ids == ["d6d32076", "9dfa4e9a"]
    assert [o.price_amount for o in offers] == [Decimal("59.80"), Decimal("49.90")]
    assert [o.legs[0].depart_at.isoformat() for o in offers] == ["2026-12-01T18:01:00+01:00"] * 2
    assert all(o.price_currency == "EUR" for o in offers)


def test_wien_zuerich_gives_two_offers_at_66_70():
    offers, errors = parse("wien-zuerich")
    assert not errors
    assert [o.price_amount for o in offers] == [Decimal("66.70")] * 2
