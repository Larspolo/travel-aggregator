"""The ÖBB parser gives the planned departure and arrival platform of each leg (#2591)."""

import json
from pathlib import Path

from app.parsers.oebb import OebbParser

FIX = Path(__file__).parent / "fixtures" / "oebbtickets.at"


def test_a_leg_gives_its_planned_platforms_and_none_when_unknown():
    body = json.loads((FIX / "search-wien-zuerich.json").read_text(encoding="utf-8"))
    prices = {c["id"]: "49.90" for c in body["connections"]}
    r = OebbParser().parse({"response": body, "prices": prices})
    legs = [leg for o in r.offers for leg in o.legs]

    feldkirch = next(leg for leg in legs if leg.from_name == "Feldkirch Bahnhof" and leg.to_name == "Buchs SG")
    assert feldkirch.from_platform == "5A-B"
    assert feldkirch.to_platform is None

    first = next(leg for leg in legs if leg.from_name == "Wien Hbf (Bahnsteige 3-12)" and leg.to_name == "Feldkirch Bahnhof")
    assert first.from_platform is None
    assert first.to_platform == "4"


def test_the_parser_version_is_bumped_for_the_platforms():
    assert tuple(map(int, OebbParser.version.split("."))) >= (1, 3, 0)  # a later ticket bumps it again (#2786)
