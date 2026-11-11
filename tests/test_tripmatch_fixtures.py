"""The fixtures of the four sources match a trip with the English names of their places (#558); the local names
of a city (Lisboa, München, Köln) match its English name through ALIASES (#558)."""

from pathlib import Path

import pytest

from app.models import Trip
from app.parsers import get_parser
from app.tripmatch import mismatch
from tests.test_tripmatch import offer

GUARDS = ("tests/fixtures/*",)   # ship_pr runs this file for these changes, also with --tested: no import leads to it (#730, #1328)

FIXTURES = Path(__file__).parent / "fixtures"

# (source, file, English origin of the first offer, English destination of the last leg of that offer)
CASES = [
    ("bahn.de", "fahrplan-amsterdam-berlin.json", "Amsterdam", "Berlin"),
    ("bahn.de", "fahrplan-amsterdam-berlin-2-adults.json", "Amsterdam", "Berlin"),
    ("bahn.de", "fahrplan-amsterdam-bern-night.json", "Amsterdam", "Bern"),
    ("bahn.de", "fahrplan-amsterdam-zuerich.json", "Amsterdam", "Zurich"),
    ("bahn.de", "fahrplan-koeln-muenchen-bahncard25.json", "Cologne", "Munich"),
    ("bahn.de", "fahrplan-koeln-muenchen.json", "Cologne", "Munich"),
    ("bahn.de", "recon-169.json", "Cologne", "Munich"),
    ("nsinternational.com", "search-amsterdam-berlin-2-adults.json", "Amsterdam", "Berlin"),
    ("nsinternational.com", "search-amsterdam-berlin-pair.json", "Amsterdam", "Berlin"),
    ("nsinternational.com", "search-amsterdam-berlin.json", "Amsterdam", "Berlin"),
    ("nsinternational.com", "search-amsterdam-london.json", "Amsterdam", "London"),
    ("nsinternational.com", "search-amsterdam-wien-nightjet.json", "Amsterdam", "Wien"),
    ("nsinternational.com", "search-rotterdam-paris.json", "Rotterdam", "Paris"),
    ("flixbus.com", "search-2-adults.json", "Amsterdam", "Berlin"),
    ("flixbus.com", "search-amsterdam-berlin.json", "Amsterdam", "Berlin"),
    ("flixbus.com", "search-amsterdam-paris.json", "Amsterdam", "Paris"),
    ("flixbus.com", "search-utrecht-berlin.json", "Utrecht", "Berlin"),
    ("kiwi.com", "return-amsterdam-lisbon.json", "Amsterdam", "Lisbon"),
    ("kiwi.com", "search-amsterdam-lisbon.json", "Amsterdam", "Lisbon"),
    ("kiwi.com", "search-amsterdam-zurich-2-adults.json", "Amsterdam", "Zurich"),
    ("kiwi.com", "search-amsterdam-zurich.json", "Amsterdam", "Zurich"),
]
IDS = [f"{source}/{name}" for source, name, _, _ in CASES]


def _offers(source, name):
    import json

    raw = json.loads((FIXTURES / source / name).read_text(encoding="utf-8"))
    return get_parser(source).parse(raw).offers


def _trip(origin, destination, day):
    return Trip(title="T", origin_text=origin, destination_text=destination, date_from=day)


def test_every_fixture_file_has_a_case():
    on_disk = sorted(f"{p.parent.name}/{p.name}" for p in FIXTURES.glob("*/*.json")
                     if p.parent.name in {"bahn.de", "nsinternational.com", "flixbus.com", "kiwi.com"}
                     # a day price response has no offers (#1196): tests/test_bahn_day_prices.py
                     and not p.name.startswith("tagesbestpreis-"))
    assert on_disk == sorted(IDS)


@pytest.mark.parametrize(("source", "name", "origin", "destination"), CASES, ids=IDS)
def test_the_english_places_and_date_of_the_fixture_give_no_warning(source, name, origin, destination):
    offers = _offers(source, name)
    assert offers
    day = offers[0].legs[0].depart_at.date()
    assert mismatch(_trip(origin, destination, day), offers) is None


@pytest.mark.parametrize(("source", "name", "origin", "destination"), CASES, ids=IDS)
def test_other_places_give_a_places_warning(source, name, origin, destination):
    offers = _offers(source, name)
    day = offers[0].legs[0].depart_at.date()
    assert mismatch(_trip("Madrid", "Rome", day), offers) == "places"


def test_the_local_names_of_munich_and_lisbon_match_the_legs():
    assert mismatch(_trip("Munich", "Lisbon", offer().legs[0].depart_at.date()),
                    [offer(from_name="München Hbf", to_name="Lisboa Oriente")]) is None
