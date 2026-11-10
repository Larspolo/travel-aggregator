"""The whole seats-left flow through the API with the Eurostar fixture: a fare with 2 seats left shows the mark on the
trip page, and a newer capture with 9 seats removes it (#1828, #1822)."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip

FIX = Path(__file__).parent / "fixtures" / "eurostar.com"
AMS_LON = FIX / "search-amsterdam-london.json"


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and an empty trip."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="eurostar.com")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def post(client, auth, trip_id, raw, captured_at):
    body = {"trip_id": trip_id, "source": "eurostar.com", "parser_version": "1.0.0",
            "captured_at": captured_at, "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["errors"] == []


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def with_plus_seats(raw, seats):
    """A copy of the payload where the Eurostar Plus fare of the 06:40 train has `seats` seats left."""
    out = copy.deepcopy(raw)
    outbound = out["response"]["data"]["journeySearch"]["outbound"]
    journey = next(j for j in outbound["journeys"] if j["timing"]["departureTime"] == "06:40")
    fare = next(f for f in journey["fares"] if f["classOfService"]["code"] == "PLUS")
    assert fare["prices"]["displayPrice"] == 82.5
    fare["seats"] = seats
    return out


def test_seats_left_mark_follows_the_newest_capture(trip):
    client, auth, trip_id = trip
    raw = load(AMS_LON)

    # the first capture: the Plus fare has 2 seats left, the Standard fare has 28 (no mark)
    post(client, auth, trip_id, raw, "2026-11-08T09:00:00Z")
    page = client.get(f"/trips/{trip_id}").text
    assert "2 seats left" in page
    assert page.count('class="badge seats-left"') == 1

    # a newer capture: the Plus fare has 9 seats left (above the limit of 5), so no mark is left
    post(client, auth, trip_id, with_plus_seats(raw, 9), "2026-11-09T09:00:00Z")
    page = client.get(f"/trips/{trip_id}").text
    assert "seats left" not in page
    assert "seats-left" not in page
