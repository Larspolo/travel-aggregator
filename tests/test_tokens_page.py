"""The API tokens page (#57)."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hash_token, make_password_hash
from app.main import app
from app.models import ApiToken, Trip

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _create(c, name="laptop"):
    r = c.post("/tokens", data={"name": name, "csrf_token": _token(c, "/tokens")})
    assert r.status_code == 200
    return re.search(r"Set API token:\s+([A-Za-z0-9_-]+)", r.text).group(1), r.text


def test_no_login_redirects():
    r = TestClient(app).get("/tokens", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=%2F")  # the target of #2103


def test_create_shows_value_once_and_stores_only_hash(sessions, client):
    value, text = _create(client, "laptop <b>")
    assert "Set server URL: http://testserver" in text and "laptop &lt;b&gt;" in text
    with sessions() as s:
        t = s.scalars(select(ApiToken)).one()
        assert t.token_hash == hash_token(value) and value not in t.token_hash
    page = client.get("/tokens").text
    assert value not in page and "laptop &lt;b&gt;" in page and "never" in page and "Revoke" in page


def test_revoke_needs_csrf_and_blocks_ingest(sessions, client):
    value, _ = _create(client)
    with sessions() as s:
        token_id = s.scalars(select(ApiToken.id)).one()
        trip = Trip(title="x")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    auth = {"Authorization": f"Bearer {value}"}
    assert client.post("/api/ingest", json={"trip_id": trip_id, "source": "x", "offers": []},
                       headers=auth).status_code != 401
    assert client.post(f"/tokens/{token_id}/revoke", follow_redirects=False).status_code == 403
    r = client.post(f"/tokens/{token_id}/revoke", data={"csrf_token": _token(client, "/tokens")},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "revoked" in client.get("/tokens").text
    assert client.post("/api/ingest", json={"trip_id": trip_id, "source": "x", "offers": []},
                       headers=auth).status_code == 401
