"""The stops between the ends of an SBB train leg (#2732), from the fixture and from small payloads."""

import json
from pathlib import Path

from app.parsers.sbb import SbbParser, stops

FIX = Path(__file__).parent / "fixtures" / "sbb.ch" / "search-basel-zuerich.json"


def _offer(service_no):
    r = SbbParser().parse(json.loads(FIX.read_text(encoding="utf-8")))
    assert r.errors == []
    return next(o for o in r.offers if any(leg.service_no == service_no for leg in o.legs))


def test_fixture_ir_leg_has_six_stops():
    leg = next(x for x in _offer("IR 1963").legs if x.service_no == "IR 1963")
    names = [s.name for s in leg.stops]
    assert len(names) == 6
    assert names[0] == "Rheinfelden" and leg.stops[0].code == "8500301"
    assert names[-1] == "Baden"


def test_fixture_ic_leg_has_no_stops():
    leg = next(x for x in _offer("IC 763").legs if x.service_no == "IC 763")
    assert leg.stops == []


def test_no_stop_points_key_gives_none():
    assert stops({"name": "x"}) is None
    assert stops(None) is None


def test_empty_name_is_skipped_and_tunnel_is_no_stop():
    journey = {"stopPoints": [
        {"place": {"id": "8500010", "name": "Basel SBB"}},
        {"place": {"id": "175", "name": "Hauenstein-Basistunnel"}},
        {"place": {"id": "8500301", "name": ""}},
        {"place": {"id": "8500302", "name": "Olten"}},
        {"place": {"id": "8503000", "name": "Zürich HB"}},
    ]}
    result = stops(journey)
    assert [(s.name, s.code) for s in result] == [("Olten", "8500302")]
