"""POST /api/ingest stores the raw capture compressed, and the price rows link to it (#53)."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.ingest import load_raw
from app.main import app
from app.models import Capture, FarePrice, Itinerary, Trip
from tests.test_ingest_api import body


def test_post_with_raw_and_offers_stores_capture_and_links_prices(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="T")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    raw = {"journeys": [{"id": "x", "price": 89.9, "name": "Zürich"}]}
    r = TestClient(app).post("/api/ingest", json=body(trip_id, raw=raw), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["created"] == 1
    with sessions() as s:
        captures = s.scalars(select(Capture)).all()
        assert len(captures) == 1 and load_raw(captures[0]) == raw
        assert s.scalar(select(Itinerary)).trip_id == trip_id
        assert [p.capture_id for p in s.scalars(select(FarePrice))] == [captures[0].id]
