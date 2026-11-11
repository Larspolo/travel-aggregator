"""The whole bicycle flow through the API with the Trainline fixture: the marks of the journeys show on the trip page,
a newer capture changes a mark, and a bahn.de fixture shows no mark (#2462, epic #2456)."""

import copy
import dataclasses
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import CurrencyRate, Itinerary, ScoreProfile, Trip
from app.profiles import from_config, save, to_config
from app.ranking import Weights
from app.parsers import parser_classes
from tests.test_bahn_whole import post as post_bahn
from tests.test_trip_booked import csrf
from tests.test_carrier_loyalty_export import _import, _only_profile
from tests.test_flixbus_whole import post as post_flixbus
from tests.test_trainline_whole import post as post_trainline

FIX = Path(__file__).parent / "fixtures"
TRAINLINE = FIX / "thetrainline.com" / "search-london-edinburgh.json"
BAHN = FIX / "bahn.de" / "fahrplan-amsterdam-berlin.json"

RESERVATION = re.compile(r'<span class="badge bike"[^>]*>bicycle: reservation</span>')
NO_BIKE = re.compile(r'<span class="badge bike"[^>]*>no bicycle</span>')


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


def post(client, auth, trip_id, source, raw, captured_at):
    body = {"trip_id": trip_id, "source": source, "parser_version": parser_classes()[source].version,
            "captured_at": captured_at, "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _journeys(node, found=None):
    """Every journey dict of the Trainline payload (the bike status sits on the journey)."""
    found = [] if found is None else found
    if isinstance(node, dict):
        if "bikeRestrictionStatus" in node:
            found.append(node)
        for v in node.values():
            _journeys(v, found)
    elif isinstance(node, list):
        for v in node:
            _journeys(v, found)
    return found


def test_the_marks_follow_the_journeys_of_the_trainline_fixture(trip):
    client, auth, trip_id = trip
    post(client, auth, trip_id, "thetrainline.com", load(TRAINLINE), "2026-11-08T09:00:00Z")
    page = client.get(f"/trips/{trip_id}").text
    assert len(RESERVATION.findall(page)) > 0
    assert len(NO_BIKE.findall(page)) > 0
    assert 'class="badge bike"' in page
    assert "bicycle: allowed" not in page


def test_a_newer_capture_changes_the_mark_of_one_journey(trip):
    client, auth, trip_id = trip
    raw = load(TRAINLINE)
    post(client, auth, trip_id, "thetrainline.com", raw, "2026-11-08T09:00:00Z")
    before = client.get(f"/trips/{trip_id}").text
    no_before, res_before = len(NO_BIKE.findall(before)), len(RESERVATION.findall(before))
    assert no_before > 0

    changed = copy.deepcopy(raw)
    journey = next(j for j in _journeys(changed) if j["bikeRestrictionStatus"] == "notAllowed")
    journey["bikeRestrictionStatus"] = "allowedWithReservation"
    post(client, auth, trip_id, "thetrainline.com", changed, "2026-11-09T09:00:00Z")
    after = client.get(f"/trips/{trip_id}").text
    assert len(NO_BIKE.findall(after)) < no_before
    assert len(RESERVATION.findall(after)) > res_before


def test_a_bahn_fixture_shows_no_bicycle_mark(trip):
    client, auth, trip_id = trip
    post(client, auth, trip_id, "bahn.de", load(BAHN), "2026-11-08T09:00:00Z")
    page = client.get(f"/trips/{trip_id}").text
    assert 'class="badge bike"' not in page
    assert "bicycle" not in page


def _bike_trip(sessions, trip_id):
    """The trip takes a bicycle (#2477: the trip value that the import keeps) and the GBP of the Trainline fares has a rate."""
    with sessions() as s:
        s.get(Trip, trip_id).bike = True
        s.add(CurrencyRate(code="GBP", eur_per_unit=Decimal("1.15"), updated_at=datetime(2026, 11, 1, tzinfo=timezone.utc)))
        s.commit()


def test_a_bicycle_trip_hides_the_flixbus_ride_and_shows_the_fee_and_the_unknown_bahn_fare(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _bike_trip(sessions, trip_id)
    post_flixbus(client, auth, trip_id, load(FIX / "flixbus.com" / "search-utrecht-berlin.json"))
    post_trainline(client, auth, trip_id, load(TRAINLINE))
    bahn = load(BAHN)
    bahn["response"]["verbindungen"][0]["angebotsPreis"] = {"betrag": 39.99, "waehrung": "EUR"}  # a price (#1621)
    post_bahn(client, auth, trip_id, bahn)
    page = client.get(f"/trips/{trip_id}?bike_fee=9").text
    assert "hidden by bicycle" in page and "flixbus.com" in page
    assert "GBP 83.10 (€95.56) price + €66 time + €9 bicycle = €170.56" in page  # the fee of a reservation fare
    assert "bicycle: not known" in page


def _set_profile_bike_fee(sessions, trip_id, fee):
    """The trip uses a profile whose bicycle fee is `fee` euros, so every page of the trip counts the same fee."""
    with sessions() as s:
        profile = save(s, "Bike", dataclasses.replace(Weights(), bike_fee=Decimal(fee)))
        s.get(Trip, trip_id).profile_id = profile.id
        s.commit()


def test_the_trainline_fee_is_the_same_on_the_trip_compare_and_shared_pages(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _bike_trip(sessions, trip_id)
    _set_profile_bike_fee(sessions, trip_id, "9")
    post_trainline(client, auth, trip_id, load(TRAINLINE))
    with sessions() as s:
        ids = [i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id).order_by(Itinerary.id))]
    total = "GBP 83.10 (€95.56) price + €66 time + €9 bicycle = €170.56"
    trip_page = client.get(f"/trips/{trip_id}").text
    compare = client.get(f"/trips/{trip_id}/compare", params={"it": ids}).text
    shared_link = client.post(f"/trips/{trip_id}/share", data={"csrf_token": csrf(client, trip_id)})
    shared = client.get(re.search(r'<pre class="share-link">([^<]+)</pre>', shared_link.text).group(1)
                        .removeprefix("http://testserver")).text
    assert total in trip_page and total in compare and total in shared


def test_the_settings_export_keeps_the_bicycle_fee_and_an_old_export_gives_zero(trip, sessions):  # noqa: F811
    client, _, _ = trip
    _only_profile(sessions, to_config(Weights(bike_fee=Decimal("9"))))
    export = client.get("/settings/export.json").json()
    assert export["profiles"][0]["config"]["bike_fee"] == "9"
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.commit()
    assert _import(client, export, export["profiles"][0]["config"]).status_code == 200
    with sessions() as s:
        assert from_config(s.query(ScoreProfile).one().config_json).bike_fee == Decimal("9")

    old = {k: v for k, v in export["profiles"][0]["config"].items() if k != "bike_fee"}
    with sessions() as s:
        s.query(ScoreProfile).delete()
        s.commit()
    assert _import(client, export, old).status_code == 200
    with sessions() as s:
        assert from_config(s.query(ScoreProfile).one().config_json).bike_fee == Decimal("0")
