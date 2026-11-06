"""The whole ingest feature through the API: a batch posted three times gives the right counts and rows (#55)."""

import copy

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import tokens
from app.main import app
from app.models import Capture, FarePrice, Itinerary, Trip
from tests.test_ingest_api import BODY


def _count(s, model):
    return s.scalar(select(func.count()).select_from(model))


def test_batch_posted_three_times(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="T")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    good = BODY["offers"][0]
    second = copy.deepcopy(good)
    second["legs"] = [second["legs"][0]]
    bad = {"price_amount": "x", "legs": []}
    body = {**copy.deepcopy(BODY), "trip_id": trip_id, "raw": {"journeys": [1, 2, 3]}, "offers": [good, bad, second]}
    client, auth = TestClient(app), {"Authorization": f"Bearer {token}"}

    def post():
        r = client.post("/api/ingest", json=body, headers=auth)
        assert r.status_code == 200
        return r.json()

    r = post()
    assert (r["created"], r["updated"], r["unchanged"], r["rejected"]) == (2, 0, 0, 1)
    assert [e["index"] for e in r["errors"]] == [1]
    with sessions() as s:
        assert (_count(s, Itinerary), _count(s, FarePrice), _count(s, Capture)) == (2, 2, 1)

    r = post()
    assert (r["created"], r["updated"], r["unchanged"], r["rejected"]) == (0, 0, 2, 1)
    with sessions() as s:
        assert (_count(s, Itinerary), _count(s, FarePrice), _count(s, Capture)) == (2, 2, 2)

    body["offers"][2] = {**second, "price_amount": 59.90}
    r = post()
    assert (r["created"], r["updated"], r["unchanged"], r["rejected"]) == (0, 1, 1, 1)
    with sessions() as s:
        assert (_count(s, Itinerary), _count(s, FarePrice), _count(s, Capture)) == (2, 3, 3)
