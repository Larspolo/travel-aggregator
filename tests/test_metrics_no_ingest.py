"""The metrics token reads only the metrics: POST /api/ingest with it gets 401 and stores nothing (P5, #1930)."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import Capture, Itinerary, Trip
from tests.test_ingest_api import body
from tests.test_metrics import _new_token
from tests.test_upcoming_page import client  # noqa: F401  (client is a fixture)


def test_metrics_token_gets_401_on_ingest_and_stores_nothing(client, sessions):  # noqa: F811
    with sessions() as s:
        trip = Trip(title="Amsterdam – Zürich")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    token = _new_token(client)

    r = TestClient(app).post("/api/ingest", json=body(trip_id), headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 401
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Itinerary)) == 0
        assert s.scalar(select(func.count()).select_from(Capture)) == 0
