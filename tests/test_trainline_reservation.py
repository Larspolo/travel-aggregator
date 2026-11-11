"""The Trainline parser stores a mandatory seat reservation as "included": Trainline books it with the ticket (#1622)."""

import json
from pathlib import Path

import pytest

from app.parsers.trainline import TrainlineParser

FIX = Path(__file__).parent / "fixtures" / "thetrainline.com"
FILES = ["search-london-edinburgh.json", "search-amsterdam-berlin.json"]


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def pairs(name):
    """(fixture leg, parsed leg) of each offer, in the order of the journey legs."""
    raw = load(name)
    search = raw["response"]["data"]["journeySearch"]
    journeys = {j["id"]: j for j in search["journeys"].values()}
    result = TrainlineParser().parse(raw)
    for offer in result.offers:
        journey = journeys[offer.external_id]
        assert len(journey["legs"]) == len(offer.legs)
        for leg_id, parsed in zip(journey["legs"], offer.legs):
            yield search["legs"][leg_id], parsed


def test_fixture_has_both_kinds_of_leg():
    flags = [bool(leg.get("isReservationMandatory")) for leg, _ in pairs("search-london-edinburgh.json")]
    assert True in flags and False in flags


@pytest.mark.parametrize("name", FILES)
def test_mandatory_reservation_is_included_and_others_are_none(name):
    seen = list(pairs(name))
    assert seen
    for leg, parsed in seen:
        if leg.get("isReservationMandatory") is True:
            assert parsed.reservation == "included"
        else:
            assert parsed.reservation is None


@pytest.mark.parametrize("name", FILES)
def test_no_trainline_fare_has_a_required_reservation(name):
    result = TrainlineParser().parse(load(name))
    assert result.offers
    assert all(o.reservation_legs == 0 for o in result.offers)


def test_version_is_1_3_0():
    assert TrainlineParser.version == "1.3.0"


def test_missing_flag_gives_none():
    raw = load("search-london-edinburgh.json")
    for leg in raw["response"]["data"]["journeySearch"]["legs"].values():
        leg.pop("isReservationMandatory", None)
    result = TrainlineParser().parse(raw)
    assert result.offers
    assert all(leg.reservation is None for o in result.offers for leg in o.legs)
