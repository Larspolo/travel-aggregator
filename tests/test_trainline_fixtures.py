"""The thetrainline.com fixtures (#975): the ids that the kept objects name exist, no personal data, small files."""

import json
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "thetrainline.com"
FILES = ["search-london-edinburgh.json", "search-amsterdam-berlin.json"]
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}", re.I)


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


@pytest.mark.parametrize("name", FILES)
def test_file_is_small_and_has_no_personal_data(name):
    path = FIXTURES / name
    assert path.stat().st_size < 300_000
    text = path.read_text(encoding="utf-8")
    assert not EMAIL.search(text)
    keys = {str(k).lower() for k in walk_keys(load(name))}
    assert not any("cookie" in k or "token" in k or "session" in k for k in keys)
    assert all(v == "REDACTED" for v in re.findall(r'"dateOfBirth": "([^"]*)"', text))
    body = load(name)["request"]["body"]
    assert all("id" not in p for p in body["passengers"])
    assert set(load(name)["response"]["data"]["journeySearch"]["passengers"]) == {"p1"}


@pytest.mark.parametrize("name", FILES)
def test_named_ids_exist(name):
    data = load(name)["response"]["data"]
    js = data["journeySearch"]
    journeys, legs, sections = js["journeys"], js["legs"], js["sections"]
    alternatives, fares = js["alternatives"], js["fares"]
    locations, carriers = data.get("locations", {}), data.get("carriers", {})
    fare_types, transport_modes = data.get("fareTypes", {}), data.get("transportModes", {})
    passenger_types = data.get("passengerTypes", {})

    assert journeys
    for journey in journeys.values():
        assert all(i in legs for i in journey["legs"])
        assert all(i in sections for i in journey["sections"])
        for section_id in journey["sections"]:
            section = sections[section_id]
            assert section["alternatives"], "a section needs at least one alternative"
            for alt_id in section["alternatives"]:
                alt = alternatives[alt_id]
                for fare_id in alt["fares"]:
                    fare = fares[fare_id]
                    assert fare["fareType"] in fare_types
                    assert fare["origin"] in locations
                    assert fare["destination"] in locations
                    for fare_leg in fare["fareLegs"]:
                        assert fare_leg["legId"] in legs
                for fp in alt["farePassengers"]:
                    for p in fp["passengers"]:
                        assert p["id"] in js["passengers"]
                        assert p["passengerType"] in passenger_types
    for leg in legs.values():
        assert leg["carrier"] in carriers
        assert leg["departureLocation"] in locations
        assert leg["arrivalLocation"] in locations
        assert leg["transportMode"] in transport_modes
