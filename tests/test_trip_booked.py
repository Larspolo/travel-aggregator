"""The owner marks an itinerary as booked (#201): POST .../booked toggles the flag, the trip page shows the mark, and the
migration 0006 upgrades and downgrades with no error."""

import re

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Itinerary, Trip
from tests.test_trip_page import ingest, offer


def _alembic(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture
def trip(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {token}"}
    ingest(client, auth, trip_id, [offer("89.90", "ICE 105")])
    yield client, trip_id
    app.dependency_overrides.pop(require_login, None)


def csrf(client, trip_id):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)


def booked_url(trip_id, itinerary):
    return f"/trips/{trip_id}/itineraries/{itinerary}/booked"


def _itinerary_id(sessions, trip_id):
    with sessions() as s:
        return s.query(Itinerary).filter_by(trip_id=trip_id).one().id


def _booked(sessions, itinerary):
    with sessions() as s:
        return s.get(Itinerary, itinerary).booked


def test_a_post_toggles_booked_and_the_row_shows_the_mark(trip, sessions):
    client, trip_id = trip
    it = _itinerary_id(sessions, trip_id)
    token = csrf(client, trip_id)
    assert "booked</span>" not in client.get(f"/trips/{trip_id}").text

    r = client.post(booked_url(trip_id, it), data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{trip_id}"
    assert _booked(sessions, it) is True
    page = client.get(f"/trips/{trip_id}").text
    assert '<span class="badge">booked</span>' in page
    assert "Not booked" in page

    client.post(booked_url(trip_id, it), data={"csrf_token": token}, follow_redirects=False)
    assert _booked(sessions, it) is False
    assert '<span class="badge">booked</span>' not in client.get(f"/trips/{trip_id}").text


def test_a_post_without_the_csrf_token_gets_403_and_changes_nothing(trip, sessions):
    client, trip_id = trip
    it = _itinerary_id(sessions, trip_id)
    csrf(client, trip_id)
    r = client.post(booked_url(trip_id, it), follow_redirects=False)
    assert r.status_code == 403
    assert _booked(sessions, it) is False


def test_an_itinerary_of_another_trip_gives_404(trip, sessions):
    client, trip_id = trip
    it = _itinerary_id(sessions, trip_id)
    with sessions() as s:
        other = Trip(title="Other")
        s.add(other)
        s.commit()
        other_id = other.id
    token = csrf(client, trip_id)
    r = client.post(booked_url(other_id, it), data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 404
    assert _booked(sessions, it) is False


def test_migration_0006_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        assert "booked" in {c["name"] for c in inspect(engine).get_columns("itineraries")}
        command.downgrade(cfg, "0005")
        assert "booked" not in {c["name"] for c in inspect(engine).get_columns("itineraries")}
        command.upgrade(cfg, "head")
        assert "booked" in {c["name"] for c in inspect(engine).get_columns("itineraries")}
    finally:
        engine.dispose()
