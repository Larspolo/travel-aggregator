"""The bahn.de fahrplan parser (#152) with the fixtures of tests/fixtures/bahn.de."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers import get_parser
from app.parsers.bahn import BahnParser
from app.schemas import utc_offset_min

FIX = Path(__file__).parent / "fixtures" / "bahn.de"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,offers,errors", [
    ("fahrplan-koeln-muenchen.json", 2, 1),
    ("fahrplan-amsterdam-zuerich.json", 2, 1),
    ("fahrplan-amsterdam-bern-night.json", 3, 0),
    ("fahrplan-koeln-muenchen-bahncard25.json", 3, 0),
])
def test_all_fixtures_give_offers(name, offers, errors):
    r = BahnParser().parse(load(name))
    assert len(r.offers) == offers
    assert len(r.errors) == errors
    for o in r.offers:
        assert isinstance(o.price_amount, Decimal)
        assert o.price_currency == "EUR"
        for leg in o.legs:
            assert leg.depart_at.tzinfo is not None


def test_no_price_is_rejected_with_reason():
    r = BahnParser().parse(load("fahrplan-koeln-muenchen.json"))
    assert r.errors == [{"index": 1, "reason": "no price (angebotsPreis)"}]


def test_bad_connection_is_rejected_and_others_stay():
    raw = load("fahrplan-koeln-muenchen-bahncard25.json")
    del raw["response"]["verbindungen"][0]["verbindungsAbschnitte"]
    r = BahnParser().parse(raw)
    assert len(r.offers) == 2
    assert r.errors[0]["index"] == 0


def test_price_and_offsets_amsterdam_zuerich():
    o = BahnParser().parse(load("fahrplan-amsterdam-zuerich.json")).offers[0]
    assert o.price_amount == Decimal("130.99")
    assert [leg.service_no for leg in o.legs] == ["IC 3021", "IC 3521", "20073", "ICE 105"]
    first, last = o.legs[0], o.legs[-1]
    assert first.depart_at.astimezone(UTC) == datetime(2026, 11, 20, 5, 54, tzinfo=UTC)
    assert utc_offset_min(first.depart_at) == 60
    assert str(first.depart_at.tzinfo) == "Europe/Amsterdam"
    assert str(last.arrive_at.tzinfo) == "Europe/Zurich"


def test_night_connection_arrives_next_day():
    o = BahnParser().parse(load("fahrplan-amsterdam-bern-night.json")).offers[0]
    assert o.legs[0].service_no == "NJ 403"
    assert o.legs[0].depart_at.date().isoformat() == "2026-11-20"
    assert o.legs[-1].arrive_at.astimezone(UTC) == datetime(2026, 11, 21, 6, 26, tzinfo=UTC)


def test_walk_is_no_leg_and_delay_keeps_order():
    o = BahnParser().parse(load("fahrplan-koeln-muenchen.json")).offers[0]
    assert [leg.service_no for leg in o.legs] == ["S12", "ICE 519"]
    assert o.fare_name == "1st class"


def test_bahncard25_discount_in_offer():
    r = BahnParser().parse(load("fahrplan-koeln-muenchen-bahncard25.json"))
    assert {o.fare_name for o in r.offers} == {"2nd class, BahnCard 25"}
    assert r.offers[0].legs[0].carrier == "DB Fernverkehr AG"


def test_response_body_only_and_registry():
    raw = load("fahrplan-koeln-muenchen.json")["response"]
    assert len(get_parser("bahn.de").parse(raw).offers) == 2
    assert get_parser("unknown") is None


def test_payload_without_list_raises():
    with pytest.raises(ValueError):
        BahnParser().parse({"response": {}})
