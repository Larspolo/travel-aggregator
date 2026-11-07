"""The "Reparse capture" button shows only on a capture with raw data (#451)."""

import re

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip
from tests.test_ingest_api import body

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Reise")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c, "/login")})
    return c, {"Authorization": f"Bearer {token}"}, trip_id


def _csrf(c, path):
    return re.search(r'csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def test_reparse_button_only_on_a_capture_with_raw_data(client, sessions):
    c, auth, trip_id = client
    raw = {"journeys": [{"id": "x", "price": 89.9}]}
    assert c.post("/api/ingest", headers=auth, json=body(trip_id, raw=raw)).status_code == 200
    assert c.post("/api/ingest", headers=auth, json=body(trip_id, captured_at="2026-11-02T10:00:00Z")).status_code == 200

    with sessions() as s:
        with_raw, without_raw = s.query(Capture).order_by(Capture.id).all()
        assert with_raw.raw_gz is not None
        assert without_raw.raw_gz is None
        with_raw_id, without_raw_id = with_raw.id, without_raw.id

    text = c.get("/captures").text
    assert f'id="reparse-{with_raw_id}"' in text
    assert f'/captures/{without_raw_id}/reparse' not in text
