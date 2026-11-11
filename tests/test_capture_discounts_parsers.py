"""The other train parsers set the discount cards of a capture where their payload names them (#1752, epic #1749)."""

import copy
import json
from pathlib import Path

from app.parsers import parser_classes
from tests.test_capture_mismatch import _setup
from tests.test_capture_travelers import _capture, _ingest

FIXTURES = Path(__file__).parent / "fixtures"
NS = FIXTURES / "nsinternational.com" / "search-amsterdam-berlin.json"
TRAINLINE = FIXTURES / "thetrainline.com" / "search-amsterdam-berlin.json"
OEBB_FARES = FIXTURES / "oebbtickets.at" / "fares-amsterdam-wien-nightjet.json"
OEBB_SEARCH = FIXTURES / "oebbtickets.at" / "search-amsterdam-wien.json"
EUROSTAR = FIXTURES / "eurostar.com" / "search-brussels-paris.json"
SNCF = FIXTURES / "sncf-connect.com" / "search-paris-lyon.json"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _parse(source, raw):
    return parser_classes()[source]().parse(raw)


def test_an_ns_capture_without_a_card_stores_an_empty_list(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="Berlin")
    _ingest(c, auth, trip_id, "nsinternational.com", _load(NS))
    assert _capture(sessions, trip_id).discounts == []


def test_ns_reads_the_card_names_of_reduction_cards_applied():
    raw = _load(NS)
    for offer in raw["response"]["data"]["travelOffers"][0]["offers"]:
        offer["reductionCardsApplied"] = ["Voordeelurenkaart", "Voordeelurenkaart", 7]
    assert _parse("nsinternational.com", raw).discounts == ["Voordeelurenkaart"]


def test_ns_without_the_field_keeps_none():
    raw = _load(NS)
    for conn in raw["response"]["data"]["travelOffers"]:
        for offer in conn["offers"]:
            offer.pop("reductionCardsApplied", None)
    assert _parse("nsinternational.com", raw).discounts is None


def test_a_trainline_capture_without_a_card_stores_an_empty_list():
    assert _parse("thetrainline.com", _load(TRAINLINE)).discounts == []


def test_trainline_reads_the_cards_of_the_request():
    raw = copy.deepcopy(_load(TRAINLINE))
    raw["request"]["body"]["cards"] = ["Railcard 16-25"]
    assert _parse("thetrainline.com", raw).discounts == ["Railcard 16-25"]


def test_trainline_response_only_keeps_none():
    raw = _load(TRAINLINE)["response"]
    assert _parse("thetrainline.com", raw).discounts is None


def test_an_oebb_fare_response_stores_an_empty_list():
    assert _parse("oebbtickets.at", _load(OEBB_FARES)).discounts == []


def test_oebb_reads_the_relevant_reductions_of_a_fare():
    raw = copy.deepcopy(_load(OEBB_FARES))
    raw["offerSections"][0]["travelClasses"][0]["offers"][0]["relevantReductions"] = ["Vorteilscard 25"]
    assert _parse("oebbtickets.at", raw).discounts == ["Vorteilscard 25"]


def test_an_oebb_search_response_keeps_none():
    assert _parse("oebbtickets.at", _load(OEBB_SEARCH)).discounts is None


def test_eurostar_has_no_card_field_and_keeps_none():
    assert _parse("eurostar.com", _load(EUROSTAR)).discounts is None


def test_sncf_has_no_card_field_and_keeps_none():
    assert _parse("sncf-connect.com", _load(SNCF)).discounts is None
