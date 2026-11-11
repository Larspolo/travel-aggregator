"""The carrier names of the sources map to one name per carrier (#2248, epic #2247)."""

import json
from pathlib import Path

import pytest

from app.carriers import CARRIERS, carrier_names
from app.parsers import parser_classes

FIX = Path(__file__).parent / "fixtures"

# The carrier names with no entry in the table yet: they stay as they are.
KEPT = {"Lumo", "CrossCountry", "VIAS Rail GmbH", "eurobahn", "National Express", "Other"}


@pytest.mark.parametrize("raw, expected", [
    ("DB Fernverkehr AG", ("Deutsche Bahn",)),
    ("deutsche bahn", ("Deutsche Bahn",)),
    ("Nederlandse Spoorwegen, DB Fernverkehr AG", ("NS", "Deutsche Bahn")),
    ("Lumo", ("Lumo",)),
    ("Nightjet", ("ÖBB",)),
    ("FlixBus B.V.", ("Flix",)),
    ("Flix", ("Flix",)),
    ("NS, nederlandse spoorwegen", ("NS",)),
    ("DB Fernverkehr AG, DB Fernverkehr AG", ("Deutsche Bahn",)),
    ("  SBB ,  ", ("SBB",)),
    (None, ()),
    ("", ()),
    ("   ", ()),
])
def test_carrier_names(raw, expected):
    assert carrier_names(raw) == expected


def test_no_source_name_is_in_two_groups():
    seen: dict[str, str] = {}
    for name, source_names in CARRIERS.items():
        for source_name in (name, *source_names):
            key = source_name.casefold()
            assert seen.setdefault(key, name) == name, f"{source_name!r} is in {seen[key]!r} and {name!r}"


def _fixture_files():
    for source, cls in parser_classes().items():
        for path in sorted((FIX / source).glob("*.json")):
            if path.name.startswith("prices-"):
                continue  # a price response: it needs its search response (tests/test_oebb_parser.py)
            yield pytest.param(cls, path, id=f"{source}/{path.name}")


@pytest.mark.parametrize("cls, path", list(_fixture_files()))
def test_each_carrier_of_a_fixture_has_one_name(cls, path):
    result = cls().parse(json.loads(path.read_text(encoding="utf-8")))
    raws = {leg.carrier for offer in result.offers for leg in offer.legs if leg.carrier}
    for raw in raws:
        for name in carrier_names(raw):
            assert name in CARRIERS or name in KEPT, f"{raw!r} gives {name!r}, which is not in the table"
