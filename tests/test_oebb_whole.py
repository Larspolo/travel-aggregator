"""The whole oebbtickets.at capture through the API: each fixture, sent as the userscript sends it, gives its connections
and fares on the trip page, and a Nightjet itinerary gets the night extras of rank:time in its breakdown (#1051)."""

import html
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from app.money import money
from app.parsers.oebb import OebbParser

FIX = Path(__file__).parent / "fixtures" / "oebbtickets.at"


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and an empty trip."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="oebbtickets.at")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def search_capture(trip_name):
    """A search capture as the userscript sends it: the timetable and the prices of its connections."""
    prices = {o["connectionId"]: str(o["price"]) for o in load(f"prices-{trip_name}.json")["offers"]
              if not o["offerError"]}
    return {"response": load(f"search-{trip_name}.json"), "prices": prices}


def fare_capture():
    return {"response": load("fares-amsterdam-wien-nightjet.json")}


def post(client, auth, trip_id, raw):
    body = {"trip_id": trip_id, "source": "oebbtickets.at", "parser_version": "1.0.0",
            "captured_at": "2026-11-08T09:00:00Z", "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def test_amsterdam_wien_shows_both_connections_with_their_prices(trip):
    client, auth, trip_id = trip
    out = post(client, auth, trip_id, search_capture("amsterdam-wien"))
    assert out["errors"] == []

    page = client.get(f"/trips/{trip_id}").text
    assert "18:01" in page
    assert "09:32" in page
    assert "09:48" in page
    assert money(Decimal("59.80"), "EUR") in page
    assert money(Decimal("49.90"), "EUR") in page


def test_the_nightjet_itinerary_shows_its_three_fares_after_the_fare_capture(trip):
    client, auth, trip_id = trip
    post(client, auth, trip_id, search_capture("amsterdam-wien"))
    out = post(client, auth, trip_id, fare_capture())
    assert out["errors"] == []

    page = client.get(f"/trips/{trip_id}").text
    assert "Seat" in page and "Couchette" in page and "Sleeper" in page
    for price in ("59.80", "124.80", "204.80"):
        assert money(Decimal(price), "EUR") in page, price


def test_wien_zuerich_shows_both_connections_at_66_70(trip):
    client, auth, trip_id = trip
    out = post(client, auth, trip_id, search_capture("wien-zuerich"))
    assert out["errors"] == []

    page = client.get(f"/trips/{trip_id}").text
    assert page.count(money(Decimal("66.70"), "EUR")) >= 2


def test_the_parser_gives_the_same_offers_as_the_api_capture():
    """The parser of the capture gives the offers that the API stored (no request is sent: P1)."""
    parsed = OebbParser().parse(search_capture("amsterdam-wien"))
    assert [o.price_amount for o in parsed.offers] == [Decimal("59.80"), Decimal("49.90")]


def breakdowns(page):
    return [html.unescape(m) for m in re.findall(r'class="breakdown"[^>]*>([^<]*)<', page)]


def test_the_nightjet_breakdown_shows_the_night_part_with_a_night_profile(trip):
    client, auth, trip_id = trip
    post(client, auth, trip_id, search_capture("amsterdam-wien"))
    post(client, auth, trip_id, fare_capture())
    night = {"hour_markup": "5", "night_hour_markup": "20", "night_adjust": "-10"}

    page = client.get(f"/trips/{trip_id}", params=night).text
    nightjet = [b for b in breakdowns(page) if "€59.80 price" in b]
    assert nightjet, breakdowns(page)
    for b in nightjet:
        assert "night travel" in b and "night hours" in b, b

    # the default profile (night_adjust 0, no night_hour_markup) adds no night part
    plain = client.get(f"/trips/{trip_id}").text
    assert not any("night" in b for b in breakdowns(plain))
