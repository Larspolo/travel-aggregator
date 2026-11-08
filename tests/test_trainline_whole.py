"""The whole thetrainline.com capture through the API: each fixture, sent as raw, gives its journeys and fares on the trip
page with their local times, and no new rows on a second post (#980, #252). The bahn.de and Trainline captures of the
Amsterdam → Berlin search give one itinerary per shared journey with a fare of each source (#980, #485)."""

import json
from datetime import timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Itinerary, Trip
from app.parsers.trainline import TrainlineParser
from app.web.pages import money
from tests.test_bahn_whole import post as post_bahn

FIX = Path(__file__).parent / "fixtures"
TRAINLINE = FIX / "thetrainline.com"
BAHN_2_ADULTS = FIX / "bahn.de" / "fahrplan-amsterdam-berlin-2-adults.json"
TRAINLINE_AMS_BER = TRAINLINE / "search-amsterdam-berlin.json"
FIXTURES = ["search-amsterdam-berlin.json", "search-london-edinburgh.json"]
SHARED_JOURNEYS = {"08:31", "10:00"}  # departure times of the journeys in both captures (the 10:31 one is Trainline only)


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and an empty trip."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="thetrainline.com")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def post(client, auth, trip_id, raw, source="thetrainline.com"):
    body = {"trip_id": trip_id, "source": source, "parser_version": "1.0.0",
            "captured_at": "2026-11-08T09:00:00Z", "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def hm(value, offset_min=None):
    """The clock time (HH:MM) of an aware datetime; with an offset, the local time that the trip page prints."""
    if offset_min is not None:
        value = value.astimezone(timezone(timedelta(minutes=offset_min)))
    return value.strftime("%H:%M")


@pytest.mark.parametrize("name", FIXTURES)
def test_each_journey_and_fare_is_on_the_trip_page_with_local_times(trip, name):
    client, auth, trip_id = trip
    raw = json.loads((TRAINLINE / name).read_text(encoding="utf-8"))
    parsed = TrainlineParser().parse(raw)
    assert parsed.offers, "the fixture has no journey"
    assert parsed.errors == []

    out = post(client, auth, trip_id, raw)
    assert out["created"] + out["updated"] + out["unchanged"] == len(parsed.offers)
    assert out["errors"] == parsed.errors

    page = client.get(f"/trips/{trip_id}").text
    for offer in parsed.offers:
        price = Decimal(offer.price_amount).quantize(Decimal("0.01"))
        assert money(price, offer.price_currency) in page, price
        assert hm(offer.legs[0].depart_at) in page, offer.legs[0].depart_at
        assert hm(offer.legs[-1].arrive_at) in page, offer.legs[-1].arrive_at


@pytest.mark.parametrize("name", FIXTURES)
def test_a_second_post_of_the_same_fixture_adds_no_row(trip, name):
    client, auth, trip_id = trip
    raw = json.loads((TRAINLINE / name).read_text(encoding="utf-8"))
    first = post(client, auth, trip_id, raw)
    second = post(client, auth, trip_id, raw)
    assert second["created"] == 0 and second["updated"] == 0
    assert second["unchanged"] == first["created"] + first["updated"] + first["unchanged"]
    assert second["errors"] == first["errors"]


def test_the_shared_journeys_are_one_itinerary_with_a_fare_of_each_source(trip, sessions):
    client, auth, trip_id = trip
    post_bahn(client, auth, trip_id, json.loads(BAHN_2_ADULTS.read_text(encoding="utf-8")))
    post(client, auth, trip_id, json.loads(TRAINLINE_AMS_BER.read_text(encoding="utf-8")))
    with sessions() as s:
        rows = s.query(Itinerary).filter_by(trip_id=trip_id).all()
        by_sources = {it.id: {f.source for f in it.fares} for it in rows}
        departs = {it.id: hm(it.legs[0].depart_at, it.legs[0].depart_offset_min) for it in rows}
    both = {departs[it.id] for it in rows if by_sources[it.id] == {"bahn.de", "thetrainline.com"}}
    only_trainline = {departs[it.id] for it in rows if by_sources[it.id] == {"thetrainline.com"}}
    assert both == SHARED_JOURNEYS, f"rows {[(departs[i], sorted(by_sources[i])) for i in by_sources]}"
    assert only_trainline == {"10:31"}
    assert len([it for it in rows if departs[it.id] in SHARED_JOURNEYS]) == len(SHARED_JOURNEYS)
