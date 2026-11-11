"""The seats left of a Flixbus connection (#1825, epic #1822): the count of `available.seats`, else None."""

import copy
import json
from pathlib import Path

from app.parsers.flixbus import FlixbusParser

FIX = Path(__file__).parent / "fixtures" / "flixbus.com"


def _raw():
    return json.loads((FIX / "search-amsterdam-berlin.json").read_text(encoding="utf-8"))


def _first_connection(raw):
    return next(iter(next(iter(raw["response"]["trips"]))["results"].values()))


def test_the_first_offer_gives_the_seats_left_of_the_fixture():
    assert FlixbusParser().parse(_raw()).offers[0].seats_left == 76


def test_a_connection_with_seats_gives_that_count():
    raw = _raw()
    _first_connection(raw)["available"] = {"seats": 3}
    assert FlixbusParser().parse(raw).offers[0].seats_left == 3


def test_a_connection_with_no_available_key_gives_none():
    raw = copy.deepcopy(_raw())
    del _first_connection(raw)["available"]
    assert FlixbusParser().parse(raw).offers[0].seats_left is None
