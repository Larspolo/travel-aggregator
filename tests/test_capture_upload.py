"""Upload a payload file on the captures page of a trip (#1338)."""

import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip

PASSWORD = "pw"
FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-amsterdam-berlin.json"


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


@pytest.fixture
def client(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


@pytest.fixture
def trip_id(sessions):
    with sessions() as s:
        t = Trip(title="Amsterdam – Berlin", origin_text="Amsterdam", destination_text="Berlin",
                 date_from=date(2026, 12, 1), travelers=1, status="planning")
        s.add(t)
        s.commit()
        return t.id


def _count(sessions, trip_id):
    with sessions() as s:
        return s.scalar(select(func.count()).select_from(Capture).where(Capture.trip_id == trip_id))


def _post(c, trip_id, source="bahn.de", content=None, name="p.json"):
    page = f"/trips/{trip_id}/captures"
    files = None if content is None else {"file": (name, content, "application/json")}
    return c.post(page + "/upload", data={"source": source, "csrf_token": _token(c, page)}, files=files,
                  follow_redirects=False)


def test_form_lists_parser_sources(client, trip_id):
    page = client.get(f"/trips/{trip_id}/captures").text
    assert "Upload a payload" in page
    assert '<option value="bahn.de">' in page
    assert 'value="manual"' not in page


def test_upload_adds_capture_and_offers(client, sessions, trip_id):
    r = _post(client, trip_id, content=FIX.read_bytes())
    assert r.status_code == 303
    assert r.headers["location"] == f"/trips/{trip_id}/captures"
    assert _count(sessions, trip_id) == 1
    with sessions() as s:
        cap = s.scalars(select(Capture).where(Capture.trip_id == trip_id)).one()
        assert cap.source == "bahn.de" and cap.parser_version and cap.raw_gz is not None
        assert cap.offer_count and cap.offer_count > 0
    trip_page = client.get(f"/trips/{trip_id}").text
    assert "No offers" not in trip_page
    assert "Berlin" in trip_page


@pytest.mark.parametrize("source,content,line", [
    ("bahn.de", None, "Select a payload file."),
    ("bahn.de", b"", "Select a payload file."),
    ("bahn.de", b"{not json", "The file is not JSON."),
    ("nosuch.site", b"{}", "Select a source that has a parser."),
    ("manual", b"{}", "Select a source that has a parser."),
])
def test_errors_store_nothing(client, sessions, trip_id, source, content, line):
    r = _post(client, trip_id, source=source, content=content)
    assert r.status_code == 400
    assert line in r.text
    assert "Upload a payload" in r.text
    assert _count(sessions, trip_id) == 0


def test_needs_login(sessions, trip_id, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    r = c.post(f"/trips/{trip_id}/captures/upload", data={"source": "bahn.de"},
               files={"file": ("p.json", FIX.read_bytes(), "application/json")}, follow_redirects=False)
    assert r.status_code in (303, 401, 403)
    assert _count(sessions, trip_id) == 0


def test_no_csrf_token_is_rejected(client, sessions, trip_id):
    r = client.post(f"/trips/{trip_id}/captures/upload", data={"source": "bahn.de"},
                    files={"file": ("p.json", FIX.read_bytes(), "application/json")}, follow_redirects=False)
    assert r.status_code in (400, 403)
    assert _count(sessions, trip_id) == 0


def test_too_large_file_is_rejected(client, sessions, trip_id, monkeypatch):
    # The middleware of app/main.py stops a body over MAX_BODY_BYTES with 413; the check of the form is for the file.
    monkeypatch.setattr("app.web.reparse.MAX_BODY_BYTES", 10)
    r = _post(client, trip_id, content=b'{"a": "' + b"x" * 20 + b'"}')
    assert r.status_code == 400 and "The file is larger than 10 bytes." in r.text
    assert _count(sessions, trip_id) == 0
