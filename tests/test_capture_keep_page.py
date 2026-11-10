"""The keep button on the raw view of a capture (#2019) and the kept mark on the captures page."""

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


def test_raw_view_offers_keep_and_then_do_not_keep(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions, raw={"a": 1})
    text = c.get(f"/captures/{cid}/raw").text
    assert "Keep" in text and "Do not keep" not in text
    assert f'action="/captures/{cid}/keep"' in text
    assert 'name="keep" value="1"' in text

    r = c.post(f"/captures/{cid}/keep", data={"keep": "1", "csrf_token": _csrf(c, f"/captures/{cid}/raw")},
               follow_redirects=False)
    assert r.status_code == 303
    text = c.get(f"/captures/{cid}/raw").text
    assert "Do not keep" in text
    assert 'name="keep" value="0"' in text


def test_captures_page_marks_only_the_kept_capture(client, sessions):
    c, auth, trip_id = client
    kept_id = _ingest(c, auth, trip_id, sessions, raw={"a": 1})
    with sessions() as s:
        s.get(Capture, kept_id).kept = True
        s.commit()
    _ingest(c, auth, trip_id, sessions, raw={"b": 2})
    rows = re.findall(r"<tr>.*?</tr>", c.get(f"/trips/{trip_id}/captures").text, flags=re.S)
    kept_rows = [r for r in rows if "kept</span>" in r]
    assert len(kept_rows) == 1
    assert f'href="/captures/{kept_id}/raw"' in kept_rows[0]
