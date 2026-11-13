"""The planned platforms of an NS International connection: the first leg has the departure platform and the last leg
the arrival platform (#2737, epic #2736)."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from app.parsers.ns import NsParser, platform

FIX = Path(__file__).parent / "fixtures" / "nsinternational.com"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def conn_at(raw, hour):
    """The connection of the fixture that departs at `hour` (the 08:00 one of the Amsterdam-Berlin search)."""
    for conn in raw["response"]["data"]["travelOffers"]:
        if conn["itinerary"]["origin"]["departure"]["plannedLocalDateTime"][11:13] == f"{hour:02d}":
            return conn
    raise AssertionError(f"no connection at {hour}:00")


def one_connection(raw, conn):
    """A payload with only this connection, so that the parse gives its offers and nothing else."""
    out = copy.deepcopy(raw)
    out["response"]["data"]["travelOffers"] = [conn]
    return out


def test_connection_at_0800_has_departure_platform_on_first_leg_and_arrival_on_last():
    r = NsParser().parse(load("search-amsterdam-berlin.json"))
    legs = [o for o in r.offers if o.legs[0].depart_at.hour == 8][0].legs
    assert len(legs) == 2
    assert legs[0].from_platform == "8b" and legs[0].to_platform is None
    assert legs[1].from_platform is None and legs[1].to_platform == "2"


def test_middle_legs_have_no_platform():
    raw = load("search-amsterdam-berlin.json")
    conn = copy.deepcopy(conn_at(raw, 8))
    conn["itinerary"]["modalities"].insert(1, {"type": "TRAIN", "code": "IC", "name": "IC", "number": "1"})
    legs = NsParser().parse(one_connection(raw, conn)).offers[0].legs
    assert len(legs) == 3
    assert [(leg.from_platform, leg.to_platform) for leg in legs] == [("8b", None), (None, None), (None, "2")]


def test_updated_platform_wins_over_platform():
    raw = load("search-amsterdam-berlin.json")
    conn = copy.deepcopy(conn_at(raw, 8))
    conn["itinerary"]["origin"]["departure"]["updatedPlatform"] = "11"
    conn["itinerary"]["destination"]["arrival"]["updatedPlatform"] = "12"
    legs = NsParser().parse(one_connection(raw, conn)).offers[0].legs
    assert legs[0].from_platform == "11"
    assert legs[-1].to_platform == "12"


def test_null_platform_gives_none():
    raw = load("search-amsterdam-berlin.json")
    conn = copy.deepcopy(conn_at(raw, 8))
    conn["itinerary"]["origin"]["departure"]["platform"] = None
    conn["itinerary"]["destination"]["arrival"]["platform"] = None
    legs = NsParser().parse(one_connection(raw, conn)).offers[0].legs
    assert legs[0].from_platform is None
    assert legs[-1].to_platform is None


def test_direct_connection_gets_both_platforms_on_its_one_leg():
    raw = load("search-amsterdam-london.json")
    conn = copy.deepcopy(raw["response"]["data"]["travelOffers"][0])
    conn["itinerary"]["origin"]["departure"]["platform"] = "3"
    conn["itinerary"]["destination"]["arrival"]["platform"] = "9"
    r = NsParser().parse(one_connection(raw, conn))
    assert len(r.offers[0].legs) == 1
    leg = r.offers[0].legs[0]
    assert (leg.from_platform, leg.to_platform) == ("3", "9")


@pytest.mark.parametrize("value,expected", [
    ("11", "11"),
    ("", None),
    ("   ", None),
    (None, None),
    ("12345678901", None),
    ("1234567890", "1234567890"),
])
def test_platform_helper_rules(value, expected):
    station = {"departure": {"platform": value, "updatedPlatform": None}}
    assert platform(station, "departure") == expected


def test_platform_helper_with_no_station_part():
    assert platform({"departure": None}, "departure") is None
    assert platform({}, "arrival") is None


@pytest.fixture
def trip(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="nsinternational.com")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def test_trip_page_shows_platform_8b_on_the_0800_connection(trip):
    client, auth, trip_id = trip
    raw = load("search-amsterdam-berlin.json")
    body = {"trip_id": trip_id, "source": "nsinternational.com", "parser_version": "1.3.0",
            "captured_at": "2026-11-03T19:41:00Z", "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    page = client.get(f"/trips/{trip_id}").text
    assert "platform 8b" in page
