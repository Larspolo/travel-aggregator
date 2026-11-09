"""The source of an uploaded payload from its file name `<source>-<id>.json` (#1339)."""

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
NO_SOURCE = "Choose the source: the file name does not name one"


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


def _post_no_source(c, trip_id, name, content=FIX.read_bytes()):
    page = f"/trips/{trip_id}/captures"
    return c.post(page + "/upload", data={"source": "", "csrf_token": _token(c, page)},
                  files={"file": (name, content, "application/json")}, follow_redirects=False)


def test_form_offers_the_file_name_first(client, trip_id):
    page = client.get(f"/trips/{trip_id}/captures").text
    assert '<option value="">From the file name</option>' in page


def test_source_comes_from_the_file_name(client, sessions, trip_id):
    r = _post_no_source(client, trip_id, "bahn.de-12.json")
    assert r.status_code == 303
    assert _count(sessions, trip_id) == 1
    with sessions() as s:
        cap = s.scalars(select(Capture).where(Capture.trip_id == trip_id)).one()
        assert cap.source == "bahn.de" and cap.raw_gz is not None


@pytest.mark.parametrize("name", ["payload.json", "nosuch.site-5.json", "manual-7.json", "bahn.de.json"])
def test_no_source_in_the_name_stores_nothing(client, sessions, trip_id, name):
    r = _post_no_source(client, trip_id, name)
    assert r.status_code == 400
    assert NO_SOURCE in r.text
    assert _count(sessions, trip_id) == 0


def test_no_file_with_no_source_stores_nothing(client, sessions, trip_id):
    page = f"/trips/{trip_id}/captures"
    r = client.post(page + "/upload", data={"source": "", "csrf_token": _token(client, page)},
                    follow_redirects=False)
    assert r.status_code == 400
    assert NO_SOURCE in r.text
    assert _count(sessions, trip_id) == 0
