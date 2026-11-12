"""Several files in one upload on the captures page: one capture and one result per good file (#2528)."""

import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip
from app.schemas import MAX_HAR_BYTES
from tests.test_har_read import bahn_entry, har

PASSWORD = "pw"
FIX = Path(__file__).parent / "fixtures"
BAHN = (FIX / "bahn.de" / "fahrplan-amsterdam-berlin.json").read_bytes()
FLIX = (FIX / "flixbus.com" / "search-amsterdam-berlin.json").read_bytes()


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


def _captures(sessions, trip_id):
    with sessions() as s:
        return s.scalars(select(Capture.source).where(Capture.trip_id == trip_id)).all()


def _post(c, trip_id, files, source=""):
    page = f"/trips/{trip_id}/captures"
    return c.post(page + "/upload", data={"source": source, "csrf_token": _token(c, page)},
                  files=[("file", f) for f in files], follow_redirects=False)


def _results(text):
    return re.findall(r"<li>([^<]*)</li>", text.split('class="upload-results"')[1].split("</ul>")[0])


def test_each_good_file_is_stored_with_its_result(client, sessions, trip_id):
    r = _post(client, trip_id, [("bahn.de-12.json", BAHN, "application/json"),
                                ("flixbus.com-14.json", FLIX, "application/json"),
                                ("notes.txt", b"hello", "text/plain")], source="")
    assert r.status_code == 200
    assert sorted(_captures(sessions, trip_id)) == ["bahn.de", "flixbus.com"]
    lines = _results(r.text)
    assert len(lines) == 3
    assert re.match(r"bahn\.de-12\.json: stored, [1-9]\d* offers?", lines[0])
    assert re.match(r"flixbus\.com-14\.json: stored, [1-9]\d* offers?", lines[1])
    assert lines[2].startswith("notes.txt: not stored")


def test_not_json_with_a_form_source(client, sessions, trip_id):
    r = _post(client, trip_id, [("a.json", BAHN, "application/json"), ("notes.txt", b"hello", "text/plain")],
              source="bahn.de")
    assert r.status_code == 200
    assert _captures(sessions, trip_id) == ["bahn.de"]
    assert "The file is not JSON." in _results(r.text)[1]


def test_form_source_applies_to_each_file(client, sessions, trip_id):
    r = _post(client, trip_id, [("x.json", BAHN, "application/json"), ("y.json", BAHN, "application/json")],
              source="bahn.de")
    assert r.status_code == 200
    assert _captures(sessions, trip_id) == ["bahn.de", "bahn.de"]


def test_har_file_gives_its_capture_count(client, sessions, trip_id):
    content = json.dumps(har(bahn_entry("fahrplan-amsterdam-berlin.json"),
                             bahn_entry("fahrplan-koeln-muenchen.json"))).encode()
    r = _post(client, trip_id, [("x.json", BAHN, "application/json"), ("b.har", content, "application/json")],
              source="bahn.de")
    assert r.status_code == 200
    assert "2 captures from the HAR file" in _results(r.text)[1]
    assert len(_captures(sessions, trip_id)) == 3


def test_no_good_file_gives_400(client, sessions, trip_id):
    r = _post(client, trip_id, [("a.txt", b"x", "text/plain"), ("b.txt", b"y", "text/plain")], source="bahn.de")
    assert r.status_code == 400
    assert len(_results(r.text)) == 2
    assert _captures(sessions, trip_id) == []


def test_21_files_store_nothing(client, sessions, trip_id):
    r = _post(client, trip_id, [(f"bahn.de-{i}.json", BAHN, "application/json") for i in range(21)])
    assert r.status_code == 400
    assert _captures(sessions, trip_id) == []


def test_files_over_the_limit_together_store_nothing(client, sessions, trip_id):
    big = b" " * (MAX_HAR_BYTES // 2) + BAHN
    r = _post(client, trip_id, [("bahn.de-1.json", big, "application/json"),
                                ("bahn.de-2.json", big, "application/json")])
    assert r.status_code in (400, 413)
    assert _captures(sessions, trip_id) == []
