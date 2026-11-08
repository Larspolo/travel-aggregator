"""A Kiwi.com capture gives its number of travelers from the `passengers` of its request (#766)."""

import json
from pathlib import Path

import pytest

from app.parsers.kiwi import KiwiParser
from tests.test_userscript_kiwi import API, FIXTURE, page  # noqa: F401  (the Playwright fixture of #332)

FIXTURES = Path(__file__).parent / "fixtures" / "kiwi.com"
PASSENGERS = {"adults": 1, "children": 0, "infants": 0, "adultsHoldBags": [0], "adultsHandBags": [0],
              "childrenHoldBags": [], "childrenHandBags": []}


def _raw(passengers=None):
    raw = {"currency": FIXTURE["currency"], "response": FIXTURE["response"]}
    if passengers is not None:
        raw["passengers"] = passengers
    return raw


def test_one_adult_gives_one_traveler():
    assert KiwiParser().parse(_raw(PASSENGERS)).travelers == 1


def test_adults_children_and_infants_are_summed():
    p = dict(PASSENGERS, adults=2, children=1, infants=1)
    assert KiwiParser().parse(_raw(p)).travelers == 4


@pytest.mark.parametrize("passengers", [None, {"adults": 0}, {"adults": "1"}, {}, "1"])
def test_a_missing_or_bad_count_gives_none(passengers):
    assert KiwiParser().parse(_raw(passengers)).travelers is None


def test_the_fixtures_of_main_give_none():
    for f in sorted(FIXTURES.glob("*.json")):
        raw = json.loads(f.read_text(encoding="utf-8"))
        assert KiwiParser().parse(raw).travelers is None, f.name


@pytest.mark.slow
def test_the_userscript_sends_the_passengers_of_the_request(page):  # noqa: F811
    request = {"query": "query SearchOneWayItinerariesQuery { onewayItineraries }",
               "variables": {"search": {"passengers": dict(PASSENGERS, adults=2)},
                             "options": {"currency": FIXTURE["currency"]}}}
    page.evaluate("""([u, b]) => fetch(u, {method: 'POST', body: b}).then(r => r.json())""",
                  [API + "?featureName=SearchOneWayItinerariesQuery", json.dumps(request)])
    page.wait_for_function("window.__ingest.length === 1")
    raw = page.evaluate("window.__ingest")[0]["body"]["raw"]
    assert raw["passengers"]["adults"] == 2
    assert page.evaluate("window.__ingest")[0]["body"]["parser_version"] == "1.2.0"
