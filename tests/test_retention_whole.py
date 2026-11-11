"""The whole capture retention feature (#207, #206): the settings page sets 30 days, one ingest deletes only the
capture of 40 days ago, and the trip page still shows all offers with their prices (#208)."""

import copy
import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, FarePrice, Trip
from tests.test_ingest_api import BODY

PASSWORD = "pw"


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


@pytest.fixture
def setup(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Amsterdam – Zürich")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    client = TestClient(app)
    client.post("/login", data={"password": PASSWORD, "csrf_token": _token(client, "/login")})
    return client, {"Authorization": f"Bearer {token}"}, trip_id


def _post(client, auth, trip_id, service_no, price, captured_at):
    offer = copy.deepcopy(BODY["offers"][0])
    offer["price_amount"] = price
    offer["legs"][0]["service_no"] = service_no
    body = {**copy.deepcopy(BODY), "trip_id": trip_id, "captured_at": captured_at.isoformat(), "offers": [offer]}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200
    assert r.json()["created"] == 1
    return r


def test_settings_30_days_deletes_only_the_capture_of_40_days(setup, sessions):
    client, auth, trip_id = setup
    now = datetime.now(UTC)
    _post(client, auth, trip_id, "ICE 105", "89.90", now - timedelta(days=40))
    _post(client, auth, trip_id, "ICE 107", "99.90", now - timedelta(days=10))
    with sessions() as s:
        old_id, recent_id = s.scalars(select(Capture.id).order_by(Capture.captured_at)).all()

    r = client.post("/settings", data={"retention": "30", "csrf_token": _token(client, "/settings")},
                    follow_redirects=False)
    assert r.status_code == 303

    _post(client, auth, trip_id, "ICE 109", "79.90", now)

    with sessions() as s:
        capture_ids = s.scalars(select(Capture.id).order_by(Capture.captured_at)).all()
        assert old_id not in capture_ids
        assert recent_id in capture_ids
        assert len(capture_ids) == 2
        assert s.scalar(select(func.count()).select_from(FarePrice)) == 3
        assert s.scalar(select(func.count()).select_from(FarePrice).where(FarePrice.capture_id.is_(None))) == 1

    page = client.get(f"/trips/{trip_id}").text
    for price in ("€89.90", "€99.90", "€79.90"):
        assert price in page
