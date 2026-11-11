"""The NS service number is the category and the number, as bahn.de gives it (#483)."""

import json
from pathlib import Path

from app.parsers.ns import NsParser

FIX = Path(__file__).parent / "fixtures" / "nsinternational.com"


def test_first_leg_has_category_and_number_and_no_carrier():
    data = json.loads((FIX / "search-amsterdam-berlin.json").read_text(encoding="utf-8"))
    leg = NsParser().parse(data).offers[0].legs[0]
    assert leg.service_no == "ICE 121"
    assert leg.carrier is None
