"""The Kiwi.com search parser (#331) with the fixtures of tests/fixtures/kiwi.com (#330)."""

import copy
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers import get_parser
from app.parsers.kiwi import KiwiParser

FIX = Path(__file__).parent / "fixtures" / "kiwi.com"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def expected_fares(raw):
    itins = raw["response"]["data"]["onewayItineraries"]["itineraries"]
    return sum(len(it["bookingOptions"]["edges"]) for it in itins)


@pytest.mark.parametrize("name", ["search-amsterdam-lisbon.json", "search-amsterdam-zurich.json"])
def test_all_fixtures_give_one_offer_per_fare(name):
    raw = load(name)
    r = KiwiParser().parse(raw)
    assert r.errors == []
    assert len(r.offers) == expected_fares(raw)


def test_registry_gives_the_kiwi_parser():
    assert isinstance(get_parser("kiwi.com"), KiwiParser)


def test_direct_flight_legs_times_and_fares():
    r = KiwiParser().parse(load("search-amsterdam-lisbon.json"))
    # the first itinerary: AMS 06:35 local (05:35Z) to LIS 08:40 local (08:40Z), one flight, two fares
    direct = [o for o in r.offers if o.legs[0].service_no == "HV5951"]
    assert len(direct) == 2
    basic = next(o for o in direct if o.fare_name == "KIWI-BASIC")
    kiwi = next(o for o in direct if o.fare_name == "KIWI")
    leg = basic.legs[0]
    assert len(basic.legs) == 1
    assert leg.mode == "flight"
    assert leg.carrier == "HV"
    assert (leg.from_code, leg.to_code) == ("AMS", "LIS")
    # the offset is localTime minus utcTimeIso: Amsterdam +01:00 in December, Lisbon +00:00
    assert leg.depart_at.isoformat() == "2026-12-01T06:35:00+01:00"
    assert leg.arrive_at.isoformat() == "2026-12-01T08:40:00+00:00"
    assert leg.depart_at.utcoffset() == timedelta(hours=1)
    assert leg.arrive_at.utcoffset() == timedelta(0)
    assert basic.price_amount == Decimal("96.00")
    assert kiwi.price_amount == Decimal("109.48")
    assert basic.price_currency == "GBP"
    assert basic.booking_url.startswith("https://www.kiwi.com/en/booking/")


def test_self_transfer_gets_two_tickets():
    r = KiwiParser().parse(load("search-amsterdam-lisbon.json"))
    # the third itinerary: pnrCount 2, the second segment has a guarantee: two tickets, one self-transfer
    st = [o for o in r.offers if [leg.service_no for leg in o.legs] == ["HV6001", "TP1923"]]
    assert st
    assert [leg.ticket for leg in st[0].legs] == [1, 2]
    assert st[0].self_transfers == 1


def test_a_broken_itinerary_is_rejected_and_the_others_are_stored():
    raw = copy.deepcopy(load("search-amsterdam-lisbon.json"))
    good = KiwiParser().parse(raw)
    del raw["response"]["data"]["onewayItineraries"]["itineraries"][0]["sector"]["sectorSegments"][0]["segment"]["source"]["localTime"]
    r = KiwiParser().parse(raw)
    assert [e["index"] for e in r.errors] == [0]
    assert "localTime" in r.errors[0]["reason"]
    assert len(r.offers) == len(good.offers) - 2


def test_reparse_gives_the_same_offers():
    raw = load("search-amsterdam-zurich.json")
    first = KiwiParser().parse(raw)
    second = KiwiParser().parse(copy.deepcopy(raw))
    assert first.offers == second.offers
    assert first.errors == second.errors == []
