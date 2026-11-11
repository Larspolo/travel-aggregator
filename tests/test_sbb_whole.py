"""The whole sbb.ch capture through the API (#1787): each fixture, sent as raw, gives all its connections and fares on
the trip page with their local times, and no new rows on a second post."""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers.sbb import SbbParser
from app.web.pages import money
from tests.test_trainline_whole import hm, post
from tests.test_trainline_whole import trip  # noqa: F401 (a fixture)

SBB = Path(__file__).parent / "fixtures" / "sbb.ch"
FIXTURES = ["search-basel-zuerich.json", "search-basel-zuerich-half-fare.json"]


def raw_of(name):
    return json.loads((SBB / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", FIXTURES)
def test_each_connection_and_fare_is_on_the_trip_page_with_local_times(trip, name):  # noqa: F811
    client, auth, trip_id = trip
    raw = raw_of(name)
    parsed = SbbParser().parse(raw)
    assert parsed.offers and parsed.errors == []
    trips = raw["response"]["data"]["trips"]["trips"]
    assert {o.legs[0].depart_at for o in parsed.offers} == {
        datetime.fromisoformat(t["legs"][0]["departure"]["time"])
        for t in trips if any(p["tripId"] == t["id"] for p in raw["prices"]["response"]["data"]["tripPrices"])}

    out = post(client, auth, trip_id, raw, source="sbb.ch")
    assert out["created"] + out["updated"] + out["unchanged"] == len(parsed.offers)
    assert out["errors"] == []

    page = client.get(f"/trips/{trip_id}").text
    for offer in parsed.offers:
        assert offer.legs[0].depart_at.utcoffset() is not None
        price = Decimal(offer.price_amount).quantize(Decimal("0.01"))
        assert money(price, offer.price_currency) in page, price
        assert hm(offer.legs[0].depart_at) in page, offer.legs[0].depart_at
        assert hm(offer.legs[-1].arrive_at) in page, offer.legs[-1].arrive_at


@pytest.mark.parametrize("name", FIXTURES)
def test_a_second_post_of_the_same_fixture_adds_no_row(trip, name):  # noqa: F811
    client, auth, trip_id = trip
    first = post(client, auth, trip_id, raw_of(name), source="sbb.ch")
    second = post(client, auth, trip_id, raw_of(name), source="sbb.ch")
    assert second["created"] == 0 and second["updated"] == 0
    assert second["unchanged"] == first["created"] + first["updated"] + first["unchanged"]
