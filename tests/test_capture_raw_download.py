"""The raw payload of a capture as a JSON file download (#1291)."""

import json
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


def test_download_is_the_raw_json_with_a_file_name(client, sessions):
    c, auth, trip_id = client
    raw = {"journeys": [{"id": "x7", "price": 89.9}], "note": "Zürich"}
    cid = _ingest(c, auth, trip_id, sessions, raw=raw)
    r = c.get(f"/captures/{cid}/raw.json")
    assert r.status_code == 200
    assert json.loads(r.content) == raw
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["content-disposition"] == f'attachment; filename="bahn.de-{cid}.json"'


def test_source_in_file_name_is_cleaned(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions, raw={"a": 1})
    with sessions() as s:
        s.get(Capture, cid).source = 'x"; evil=1/../b'
        s.commit()
    r = c.get(f"/captures/{cid}/raw.json")
    assert r.headers["content-disposition"] == f'attachment; filename="xevil1..b-{cid}.json"'


def test_no_raw_gives_404(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions)
    with sessions() as s:
        s.get(Capture, cid).raw_gz = None
        s.commit()
    assert c.get(f"/captures/{cid}/raw.json").status_code == 404


def test_unknown_id_gives_404(client):
    c, _, _ = client
    assert c.get("/captures/999999/raw.json").status_code == 404


def test_raw_page_links_to_the_download(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions, raw={"a": 1})
    assert f'href="/captures/{cid}/raw.json"' in c.get(f"/captures/{cid}/raw").text


def test_no_login_goes_to_login(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions, raw={"a": 1})
    r = TestClient(app).get(f"/captures/{cid}/raw.json", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert "/login" in r.headers["location"]
