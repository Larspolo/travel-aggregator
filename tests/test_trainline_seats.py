"""The seats left of a Trainline fare (#1826, epic #1822): the count of the kept fare, else None."""

import json
from pathlib import Path

from app.parsers.trainline import TrainlineParser

FIX = Path(__file__).parent / "fixtures" / "thetrainline.com"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_london_edinburgh_gives_seats_left():
    offers = TrainlineParser().parse(load("search-london-edinburgh.json")).offers
    counts = [o.seats_left for o in offers]
    assert 7 in counts
    assert set(counts) <= {7, None}


def test_amsterdam_berlin_gives_no_seats_left():
    offers = TrainlineParser().parse(load("search-amsterdam-berlin.json")).offers
    assert offers
    assert all(o.seats_left is None for o in offers)
