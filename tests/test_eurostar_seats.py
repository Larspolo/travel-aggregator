"""The seats left of a Eurostar fare (#1823, #1824): the parser reads the `availabilityOfClassOfService` of each fare (#2199); a fare with no count
gets None (P5: the payload is untrusted)."""

import copy
import json
from pathlib import Path

from app.parsers.eurostar import EurostarParser

FIX = Path(__file__).parent / "fixtures" / "eurostar.com"


def load():
    return json.loads((FIX / "search-amsterdam-london.json").read_text(encoding="utf-8"))


def first_journey_fares(raw):
    return raw["response"]["data"]["journeySearch"]["outbound"]["journeys"][0]["fares"]


def seats_by_fare(raw):
    offers = EurostarParser().parse(raw).offers
    return {o.fare_name: o.seats_left for o in offers if o.legs[0].depart_at.strftime("%H:%M") == "06:40"}


def test_the_fixture_gives_the_seats_left_of_each_fare():
    assert seats_by_fare(load()) == {"Eurostar Standard": 161, "Eurostar Plus": 63, "Eurostar Premier": 12}


def test_a_fare_with_null_seats_or_no_seats_key_gives_none():
    raw = copy.deepcopy(load())
    fares = first_journey_fares(raw)
    fares[0]["availabilityOfClassOfService"] = None
    del fares[1]["availabilityOfClassOfService"]
    assert seats_by_fare(raw) == {"Eurostar Standard": None, "Eurostar Plus": None, "Eurostar Premier": 12}
