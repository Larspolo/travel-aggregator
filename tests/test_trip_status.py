"""The trip status values of docs/SPEC.md section 2: planning, booked, archived (#73)."""

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app import tokens
from app.main import app


@pytest.fixture
def client(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def test_new_trip_is_planning(client):
    c, auth = client
    trip = c.post("/api/trips", json={"title": "Utrecht – Berlin"}, headers=auth).json()
    assert trip["status"] == "planning"
    assert [t["id"] for t in c.get("/api/trips?status=planning", headers=auth).json()] == [trip["id"]]
    booked = c.post("/api/trips", json={"title": "x", "status": "booked"}, headers=auth).json()
    assert booked["status"] == "booked"


def test_active_is_rejected(client):
    c, auth = client
    assert c.post("/api/trips", json={"title": "x", "status": "active"}, headers=auth).status_code == 422


def test_migration_changes_active(empty_database_url):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0002")
    engine = create_engine(empty_database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO trips (title) VALUES ('a')"))
            assert conn.execute(text("SELECT status FROM trips")).scalar() == "active"
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            assert conn.execute(text("SELECT status FROM trips")).scalar() == "planning"
            conn.execute(text("INSERT INTO trips (title) VALUES ('b')"))
            assert conn.execute(text("SELECT count(*) FROM trips WHERE status = 'planning'")).scalar() == 2
        command.downgrade(cfg, "-1")
        with engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM trips WHERE status = 'active'")).scalar() == 2
    finally:
        engine.dispose()
