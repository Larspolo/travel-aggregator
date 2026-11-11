"""Each parser names its personal keys and its URL query names (#1903): the redacted payload gives the same result."""

import json
from pathlib import Path

import pytest

from app.parsers import parser_classes
from app.redact import PERSONAL_KEYS, redact

FIXTURES = Path(__file__).parent / "fixtures"
CLASSES = parser_classes()


def fixture_files():
    return [(source, f) for source in CLASSES for f in sorted((FIXTURES / source).glob("*.json"))]


@pytest.mark.parametrize("source", list(CLASSES))
def test_every_parser_names_its_keys(source):
    cls = CLASSES[source]
    assert isinstance(cls.redact_keys, frozenset)
    assert isinstance(cls.url_keep, frozenset)
    assert all(isinstance(k, str) and k for k in cls.redact_keys | cls.url_keep)


def outcome(parse, raw):
    """The result of `parse(raw)`, or its error: a fixture that is no whole capture (a price list) must fail the same way."""
    try:
        return parse(raw)
    except ValueError as e:
        return ("error", str(e))


@pytest.mark.parametrize("source,path", fixture_files(), ids=lambda v: getattr(v, "name", str(v)))
def test_redacted_fixture_gives_the_same_result(source, path):
    cls = CLASSES[source]
    raw = json.loads(path.read_text(encoding="utf-8"))
    redacted = redact(raw, PERSONAL_KEYS | cls.redact_keys, cls.url_keep)
    before = outcome(cls().parse, raw)
    after = outcome(cls().parse, redacted)
    if isinstance(before, tuple):
        assert after == before
        return
    assert after.offers == before.offers
    assert after.travelers == before.travelers
    assert after.discounts == before.discounts
    assert after.day_prices == before.day_prices
    assert after.errors == before.errors
