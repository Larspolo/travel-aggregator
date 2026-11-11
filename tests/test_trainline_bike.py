"""The bicycle transport of a Trainline journey (#2458, epic #2456): read from the journey, one value per fare."""

import json
from pathlib import Path

from app.parsers.trainline import TrainlineParser, bike

FIX = Path(__file__).parent / "fixtures" / "thetrainline.com"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_allowed_with_reservation_gives_reservation():
    raw = load("search-london-edinburgh.json")
    journeys = raw["response"]["data"]["journeySearch"]["journeys"]
    result = TrainlineParser().parse(raw)
    ids = [j["id"] for j in journeys.values() if j.get("bikeRestrictionStatus") == "allowedWithReservation"]
    assert ids
    for jid in ids:
        fares = [o for o in result.offers if o.external_id == jid]
        assert fares
        assert all(o.bike == "reservation" for o in fares)


def test_not_allowed_gives_no():
    raw = load("search-london-edinburgh.json")
    journeys = raw["response"]["data"]["journeySearch"]["journeys"]
    result = TrainlineParser().parse(raw)
    ids = [j["id"] for j in journeys.values() if j.get("bikeRestrictionStatus") == "notAllowed"]
    assert ids
    for jid in ids:
        fares = [o for o in result.offers if o.external_id == jid]
        assert fares
        assert all(o.bike == "no" for o in fares)


def test_missing_or_unknown_status_gives_none():
    raw = load("search-london-edinburgh.json")
    journeys = raw["response"]["data"]["journeySearch"]["journeys"]
    for j in journeys.values():
        j.pop("bikeRestrictionStatus", None)
    result = TrainlineParser().parse(raw)
    assert result.offers
    assert all(o.bike is None for o in result.offers)


def test_unknown_value_gives_none():
    raw = load("search-london-edinburgh.json")
    for j in raw["response"]["data"]["journeySearch"]["journeys"].values():
        j["bikeRestrictionStatus"] = "somethingNew"
    result = TrainlineParser().parse(raw)
    assert result.offers
    assert all(o.bike is None for o in result.offers)


def test_non_string_value_gives_none():
    assert bike(["allowed"]) is None
    assert bike(None) is None


def test_allowed_gives_allowed():
    assert bike("allowed") == "allowed"
