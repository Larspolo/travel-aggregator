"""The mandatory seat reservation through the whole flow (#1627, epic #1618): the sources' payloads go through the ingest
API, and the trip page shows the reservation mark and the fee (#1620, #1621, #1623, #1624)."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip
from tests.test_bahn_whole import post as post_bahn
from tests.test_reservation_fee import _totals
from tests.test_trainline_whole import post as post_trainline

FIX = Path(__file__).parent / "fixtures"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and an empty trip."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="reservation")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def ingest_all(client, auth, trip_id):
    """The three captures of the feature: the bahn.de night train (NJ 403 included), the bahn.de Amsterdam - Berlin
    search with a test price on connection 3 (GV 327 required, #1621), and the Trainline London - Edinburgh search."""
    night = load(FIX / "bahn.de" / "fahrplan-amsterdam-bern-night.json")
    berlin = copy.deepcopy(load(FIX / "bahn.de" / "fahrplan-amsterdam-berlin.json"))
    berlin["response"]["verbindungen"][3]["angebotsPreis"] = {"betrag": 39.99, "waehrung": "EUR"}
    trainline = load(FIX / "thetrainline.com" / "search-london-edinburgh.json")
    assert post_bahn(client, auth, trip_id, night)["created"] >= 1
    assert post_bahn(client, auth, trip_id, berlin)["created"] >= 1
    assert post_trainline(client, auth, trip_id, trainline)["created"] >= 1


def rows(page):
    """The fare rows of the trip page (one per fare), as their text."""
    return [part.split("</div>", 1)[0] for part in page.split('<div class="fare">')[1:]]


def test_the_gv_327_fare_shows_the_reservation_fee_and_the_mark(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest_all(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}?reservation_fee=10").text
    gv = [r for r in rows(page) if "reservation required" in r]
    assert len(gv) == 1 and "€39.99" in gv[0], rows(page)   # the test price of connection 3 (GV 327)
    assert "reservation =" in page and "€10 reservation" in page


def test_only_the_gv_327_fare_has_the_mark(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest_all(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert page.count("reservation required") == 1
    assert "€10 reservation" not in page


def test_with_the_fee_at_zero_every_score_is_the_same_as_without_reservation_data(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest_all(client, auth, trip_id)
    default = client.get(f"/trips/{trip_id}").text
    zero = client.get(f"/trips/{trip_id}?reservation_fee=0").text
    assert _totals(default) == _totals(zero) and "reservation =" not in default
