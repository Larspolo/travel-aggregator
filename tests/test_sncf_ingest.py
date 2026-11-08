"""A raw capture of the SNCF Connect search (#983, the userscript of userscripts/sncf.user.js) is ingested: the server
parses the fixture into its offers (tests/fixtures/sncf-connect.com)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import tokens
from app.main import app
from app.models import Itinerary, Trip

FIXTURE = json.loads((Path(__file__).resolve().parent / "fixtures" / "sncf-connect.com" / "search-paris-lyon.json")
                     .read_text("utf-8"))


@pytest.fixture
def setup(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Paris to Lyon", origin_text="Paris", destination_text="Lyon", status="planning")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    return TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id


def test_sncf_capture_is_ingested_into_the_trip(setup, sessions):
    client, auth, trip_id = setup
    body = {"source": "sncf-connect.com", "parser_version": "1.0.0", "captured_at": "2026-11-08T10:00:00+00:00",
            "page_url": "https://www.sncf-connect.com/app/home/shop/results/outward", "trip_id": trip_id,
            "raw": {"url": FIXTURE["url"], "method": "POST", "request": FIXTURE["request"],
                    "response": FIXTURE["response"]}}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    with sessions() as s:
        stored = s.scalar(select(func.count()).select_from(Itinerary).where(Itinerary.trip_id == trip_id))
    assert stored > 0
