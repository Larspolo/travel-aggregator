"""GET and POST /api/trips (part of #2): the userscript lists the trips and makes a new one; both need a token."""

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.main import app


@pytest.fixture
def client(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def test_create_and_list_trips(client):
    c, auth = client
    r = c.post("/api/trips", json={"title": " Amsterdam – Zürich ", "origin_text": "Amsterdam",
                                   "destination_text": "Zürich", "date_from": "2026-12-20"}, headers=auth)
    assert r.status_code == 201
    trip = r.json()
    assert trip["title"] == "Amsterdam – Zürich" and trip["travelers"] == 1 and trip["status"] == "planning"
    second = c.post("/api/trips", json={"title": "Utrecht – Berlin"}, headers=auth).json()
    assert [t["id"] for t in c.get("/api/trips", headers=auth).json()] == [second["id"], trip["id"]]
    assert len(c.get("/api/trips?status=planning", headers=auth).json()) == 2
    assert c.get("/api/trips?status=archived", headers=auth).json() == []


@pytest.mark.parametrize("body", [{}, {"title": ""}, {"title": "x", "travelers": 0},
                                  {"title": "x", "date_from": "2026-12-20", "date_to": "2026-12-19"}])
def test_bad_trips_get_422(client, body):
    c, auth = client
    assert c.post("/api/trips", json=body, headers=auth).status_code == 422


def test_both_need_a_token(client):
    c, _ = client
    assert c.get("/api/trips").status_code == 401
    assert c.post("/api/trips", json={"title": "x"}).status_code == 401
