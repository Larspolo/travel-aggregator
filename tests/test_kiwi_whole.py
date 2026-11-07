"""The whole Kiwi.com flight capture through the API (#333, epic of #329): each fixture of tests/fixtures/kiwi.com
gives its flight offers on the trip page, and a flight and a train of one trip are in one ranked list with the
airport time in the breakdown of the flight row."""

import html
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import CurrencyRate, Trip
from app.parsers.kiwi import KiwiParser
from tests.test_trip_page import ingest
from tests.test_trip_ranking_page import direct

FIX = Path(__file__).parent / "fixtures" / "kiwi.com"
FIXTURES = ["search-amsterdam-lisbon.json", "search-amsterdam-zurich.json"]


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and an empty trip."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Lisbon", origin_text="Amsterdam", destination_text="Lisbon")
        s.add_all([t, CurrencyRate(code="GBP", eur_per_unit=Decimal("1.15"), updated_at=datetime(2026, 11, 1, tzinfo=UTC))])
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def post_capture(client, auth, trip_id, raw):
    body = {"trip_id": trip_id, "source": "kiwi.com", "parser_version": KiwiParser.version,
            "captured_at": "2026-11-07T08:00:00Z", "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", FIXTURES)
def test_each_flight_offer_of_the_fixture_is_on_the_trip_page(trip, name):
    client, auth, trip_id = trip
    raw = load(name)
    parsed = KiwiParser().parse(raw)
    assert parsed.errors == []

    out = post_capture(client, auth, trip_id, raw)
    assert out["created"] + out["updated"] + out["unchanged"] == len(parsed.offers)
    assert out["errors"] == []

    page = client.get(f"/trips/{trip_id}").text
    for o in parsed.offers:
        assert o.legs[0].service_no in page, o.legs[0].service_no
        assert html.escape(o.fare_name) in page, o.fare_name


def test_a_flight_and_a_train_are_in_one_ranked_list_with_the_airport_time(trip):  # noqa: F811
    client, auth, trip_id = trip
    post_capture(client, auth, trip_id, load("search-amsterdam-lisbon.json"))
    # the train offer of the same trip, 4 hours, no transfer: 150 price + 60 time = 210
    ingest(client, auth, trip_id, [direct("150.00")])

    page = client.get(f"/trips/{trip_id}").text
    assert "€150 price + €60 time = €210" in page  # the train row
    assert "HV5951" in page  # the flight row
    assert "airport time" in page  # the flight row shows the buffer of the Advanced values (#99)
    # the flight: 110.40 price + 46.25 time (185 min, UTC) + 37.50 airport time = 194.15, below the train of 210
    assert "GBP 96 (€110.40) price + €46.25 time + €37.50 airport time = €194.15" in page
    assert page.index("= €194.15") < page.index("= €210")
