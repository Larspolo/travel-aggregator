"""The raw payload of a capture on its own page (#1290)."""

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


def _ingest(c, auth, trip_id, sessions, **kw):
    assert c.post("/api/ingest", headers=auth, json=body(trip_id, **kw)).status_code == 200
    with sessions() as s:
        return s.query(Capture).order_by(Capture.id.desc()).first().id


def test_raw_page_shows_formatted_json(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions, raw={"journeys": [{"id": "x7", "price": 89.9}], "note": "Zürich"})
    r = c.get(f"/captures/{cid}/raw")
    assert r.status_code == 200
    assert '&#34;journeys&#34;: [' in r.text or '"journeys": [' in r.text
    assert "x7" in r.text and "89.9" in r.text and "Zürich" in r.text
    assert f'href="/captures/{cid}/raw"' in c.get("/captures").text


def test_script_value_is_text(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions, raw={"x": "<script>alert(1)</script>"})
    text = c.get(f"/captures/{cid}/raw").text
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text


def test_large_payload_shows_size_note(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions, raw={"big": "a" * 250_000})
    text = c.get(f"/captures/{cid}/raw").text
    assert re.search(r"The payload is \d+ KB; download it to see all of it\.", text)
    assert "a" * 250_000 not in text


def test_small_payload_has_no_size_note(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions, raw={"a": 1})
    assert "download it to see all" not in c.get(f"/captures/{cid}/raw").text


def test_no_raw_and_unknown_id(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions)
    text = c.get("/captures").text
    assert "No raw payload" in text
    assert f"/captures/{cid}/raw" not in text
    assert c.get("/captures/999999/raw").status_code == 404


def test_no_login_goes_to_login(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions, raw={"a": 1})
    r = TestClient(app).get(f"/captures/{cid}/raw", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert "/login" in r.headers["location"]
