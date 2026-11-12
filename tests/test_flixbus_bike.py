"""The bicycle transport of a Flixbus connection (#2459, epic #2456): "no", "reservation", or None."""

import copy
import json
from pathlib import Path

from app.parsers.flixbus import FlixbusParser

FIX = Path(__file__).parent / "fixtures" / "flixbus.com"


def _raw():
    return json.loads((FIX / "search-utrecht-berlin.json").read_text(encoding="utf-8"))


def _first_connection(raw):
    return next(iter(next(iter(raw["response"]["trips"]))["results"].values()))


def _bike_of_first(raw):
    return FlixbusParser().parse(raw).offers[0].bike


def test_every_fare_of_the_fixture_gives_no_bike():
    offers = FlixbusParser().parse(_raw()).offers
    assert offers and all(o.bike == "no" for o in offers)


def test_bikes_allowed_with_slots_out_of_the_no_bikes_period_gives_reservation():
    raw = copy.deepcopy(_raw())
    conn = _first_connection(raw)
    conn["restrictions"]["bikes_allowed"] = True
    conn["available"]["bike_slots"] = 2
    conn["departure"]["date"] = "2026-10-31T07:15:00+01:00"  # the day before the period of the fixture
    assert _bike_of_first(raw) == "reservation"


def test_a_departure_on_the_first_day_of_the_no_bikes_period_gives_no():
    raw = copy.deepcopy(_raw())
    conn = _first_connection(raw)
    conn["restrictions"]["bikes_allowed"] = True
    conn["available"]["bike_slots"] = 2
    conn["departure"]["date"] = "2026-11-01T07:15:00+01:00"
    assert _bike_of_first(raw) == "no"


def test_a_departure_on_the_last_day_of_the_no_bikes_period_gives_no():
    raw = copy.deepcopy(_raw())
    conn = _first_connection(raw)
    conn["restrictions"]["bikes_allowed"] = True
    conn["available"]["bike_slots"] = 2
    conn["departure"]["date"] = "2027-02-28T23:30:00+01:00"
    assert _bike_of_first(raw) == "no"


def test_a_connection_with_no_restrictions_and_no_available_gives_none():
    raw = copy.deepcopy(_raw())
    conn = _first_connection(raw)
    del conn["restrictions"]
    del conn["available"]
    conn["departure"]["date"] = "2026-10-31T07:15:00+01:00"
    assert _bike_of_first(raw) is None


def test_bikes_not_allowed_gives_no():
    raw = copy.deepcopy(_raw())
    conn = _first_connection(raw)
    conn["restrictions"]["bikes_allowed"] = False
    conn["available"]["bike_slots"] = 2
    conn["departure"]["date"] = "2026-10-31T07:15:00+01:00"
    assert _bike_of_first(raw) == "no"


def test_a_bad_no_bikes_period_is_ignored():
    raw = copy.deepcopy(_raw())
    conn = _first_connection(raw)
    conn["restrictions"]["bikes_allowed"] = True
    conn["available"]["bike_slots"] = 2
    conn["departure"]["date"] = "2026-11-01T07:15:00+01:00"
    raw["response"]["no_bikes_period"] = {"from": "not a date", "to": None}
    assert _bike_of_first(raw) == "reservation"


def test_the_parser_version_is_1_3_0():
    assert FlixbusParser.version == "1.3.0"
