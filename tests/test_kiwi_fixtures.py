"""The kiwi.com fixtures: one trimmed search response per file, with no personal data (#330)."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "kiwi.com"
FILES = sorted(FIXTURES.glob("search-*.json"))
FORBIDDEN_KEYS = {"token", "serverToken", "searchSessionId", "shareId", "wishlistItineraryInfo", "server", "id"}


def _walk(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_one_fixture_per_captured_search():
    assert [path.name for path in FILES] == ["search-amsterdam-lisbon.json", "search-amsterdam-zurich.json"]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_fixture_has_priced_itineraries(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["currency"] == "gbp"
    itineraries = doc["response"]["data"]["onewayItineraries"]["itineraries"]
    assert itineraries
    for itinerary in itineraries:
        assert Decimal(itinerary["price"]["amount"]) > 0
        assert itinerary["bookingOptions"]["edges"]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_fixture_has_no_tokens_or_session_values(path):
    text = path.read_text(encoding="utf-8")
    doc = json.loads(text)
    for key, value in _walk(doc):
        assert key not in FORBIDDEN_KEYS, key
        if key == "bookingUrl":
            assert "token=REDACTED" in value or "token=" not in value
    for word in ("passengerDetails", "firstName", "lastName", "cookie", "email"):
        assert word.lower() not in text.lower(), word
    assert "@" not in text


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_fixture_is_small(path):
    assert path.stat().st_size < 32 * 1024


def test_lisbon_has_a_self_transfer():
    doc = json.loads((FIXTURES / "search-amsterdam-lisbon.json").read_text(encoding="utf-8"))
    counts = [it["pnrCount"] for it in doc["response"]["data"]["onewayItineraries"]["itineraries"]]
    assert 2 in counts
