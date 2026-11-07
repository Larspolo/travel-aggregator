"""POST /api/ingest returns a warning when the offers do not match the trip (#555); the offers are stored anyway."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import tokens
from app.main import app
from app.models import FarePrice, Trip
from tests.test_ingest_api import body


def post_for(sessions, **trip_fields):
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="T", **trip_fields)
        s.add(trip)
        s.commit()
        trip_id = trip.id
    r = TestClient(app).post("/api/ingest", json=body(trip_id), headers={"Authorization": f"Bearer {token}"})
    return r, trip_id


def test_the_correct_trip_gives_no_warning(sessions):
    r, _ = post_for(sessions, origin_text="Amsterdam", destination_text="Zürich", date_from=date(2026, 12, 20))
    assert r.status_code == 200 and r.json()["warning"] is None


def test_a_wrong_destination_gives_a_warning_and_stores_the_offers(sessions):
    r, _ = post_for(sessions, origin_text="Amsterdam", destination_text="Lisboa", date_from=date(2026, 12, 20))
    assert r.status_code == 200
    assert r.json()["warning"] == "These offers do not match the trip (places)"
    assert r.json()["created"] == 1
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(FarePrice)) == 1


def test_a_wrong_date_gives_a_date_warning(sessions):
    r, _ = post_for(sessions, origin_text="Amsterdam", destination_text="Zürich", date_from=date(2026, 12, 21))
    assert r.json()["warning"] == "These offers do not match the trip (date)"
