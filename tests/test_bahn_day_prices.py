"""The bahn.de day price response (`tagesbestpreis`, #1196): the cheapest price of each day, fail soft."""

import copy
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers.bahn import BahnParser

FIX = Path(__file__).parent / "fixtures" / "bahn.de"
DAY_FILES = sorted(FIX.glob("tagesbestpreis-*.json"))


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_first_fixture_gives_the_day_price():
    r = BahnParser().parse(_load("tagesbestpreis-amsterdam-zuerich-2026-12-01.json"))
    assert [(d.day, d.price_amount, d.price_currency) for d in r.day_prices] == [(date(2026, 12, 1), Decimal("49.99"), "EUR")]
    assert isinstance(r.day_prices[0].price_amount, Decimal)
    assert r.offers == [] and r.errors == [] and r.travelers == 1


def test_two_days_in_one_response_give_one_price_each():
    a = _load("tagesbestpreis-amsterdam-zuerich-2026-12-01.json")
    b = _load("tagesbestpreis-amsterdam-zuerich-2026-12-02.json")
    a["response"]["intervalle"] += b["response"]["intervalle"]
    r = BahnParser().parse(a["response"])
    assert [(d.day, str(d.price_amount)) for d in r.day_prices] == [(date(2026, 12, 1), "49.99"), (date(2026, 12, 2), "49.99")]


@pytest.mark.parametrize("bad", [{"ab": None}, {"preis": None}, {"preis": {"waehrung": "EUR"}}, {"ab": "not a date"}])
def test_bad_interval_is_an_error_and_others_parse(bad):
    raw = copy.deepcopy(_load("tagesbestpreis-amsterdam-zuerich-2026-12-01.json"))
    raw["response"]["intervalle"][5].update(bad)  # the cheapest interval (49.99)
    r = BahnParser().parse(raw)
    assert [e["index"] for e in r.errors] == [5]
    assert [str(d.price_amount) for d in r.day_prices] == ["57.99"]


def test_fixtures_have_no_private_data():
    assert len(DAY_FILES) == 2
    for f in DAY_FILES:
        text = f.read_text(encoding="utf-8").lower()
        for word in ("cookie", "authorization", "token", "@gmail", "bearer"):
            assert word not in text, (f.name, word)


@pytest.mark.parametrize("name", ["fahrplan-amsterdam-zuerich.json", "recon-169.json"])
def test_offer_responses_have_no_day_prices(name):
    r = BahnParser().parse(_load(name))
    assert r.day_prices == [] and r.offers
