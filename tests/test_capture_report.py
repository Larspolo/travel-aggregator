"""The raw payload of a capture for a bug report, with the personal values REDACTED (#1904)."""

import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip
from app.parsers.bahn import BahnParser

PASSWORD = "pw"
FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen-bahncard25.json"


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _personal_payload():
    """The fixture with a traveler name and a BahnCard number in its request."""
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    traveler = raw["request"]["reisende"][0]
    traveler.update({"firstName": "Erika", "lastName": "Mustermann", "cardNumber": "7081 1234 5678 9012"})
    return raw


@pytest.fixture
def client(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        t = Trip(title="Köln – München", origin_text="Köln", destination_text="München",
                 date_from=date(2026, 12, 1), travelers=1, status="planning")
        s.add(t)
        s.commit()
        trip_id = t.id
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c, trip_id


def _upload(c, trip_id, raw_bytes, source="bahn.de", name="p.json"):
    page = f"/trips/{trip_id}/captures"
    return c.post(page + "/upload", data={"source": source, "csrf_token": _token(c, page)},
                  files={"file": (name, raw_bytes, "application/json")}, follow_redirects=False)


def _capture_id(sessions):
    with sessions() as s:
        return s.query(Capture).order_by(Capture.id.desc()).first().id


def test_report_redacts_the_personal_values_and_keeps_the_response(client, sessions):
    c, trip_id = client
    raw = _personal_payload()
    _upload(c, trip_id, json.dumps(raw).encode())
    cid = _capture_id(sessions)
    r = c.get(f"/captures/{cid}/report.json")
    assert r.status_code == 200
    report = json.loads(r.content)
    traveler = report["request"]["reisende"][0]
    assert traveler["firstName"] == "REDACTED"
    assert traveler["lastName"] == "REDACTED"
    assert traveler["cardNumber"] == "REDACTED"
    assert report["response"] == raw["response"]
    assert "Erika" not in r.text and "7081 1234" not in r.text
    assert r.headers["content-disposition"] == f'attachment; filename="bahn.de-{cid}-report.json"'


def test_report_gives_the_same_offers_when_uploaded(client, sessions):
    c, trip_id = client
    raw = _personal_payload()
    _upload(c, trip_id, json.dumps(raw).encode())
    cid = _capture_id(sessions)
    report_bytes = c.get(f"/captures/{cid}/report.json").content
    assert BahnParser().parse(json.loads(report_bytes)).offers == BahnParser().parse(raw).offers
    r = _upload(c, trip_id, report_bytes, name="report.json")
    assert r.status_code in (200, 302, 303)
    assert _capture_id(sessions) != cid


def test_report_needs_a_raw_payload(client, sessions):
    c, trip_id = client
    _upload(c, trip_id, json.dumps(_personal_payload()).encode())
    cid = _capture_id(sessions)
    with sessions() as s:
        s.get(Capture, cid).raw_gz = None
        s.commit()
    assert c.get(f"/captures/{cid}/report.json").status_code == 404


def test_unknown_id_gives_404(client):
    c, _ = client
    assert c.get("/captures/999999/report.json").status_code == 404


def test_report_page_link_is_on_the_raw_page(client, sessions):
    c, trip_id = client
    _upload(c, trip_id, json.dumps(_personal_payload()).encode())
    cid = _capture_id(sessions)
    page = c.get(f"/captures/{cid}/raw").text
    assert f'href="/captures/{cid}/report.json"' in page
    assert "Download for a bug report" in page


def test_no_login_goes_to_login(client, sessions):
    c, trip_id = client
    _upload(c, trip_id, json.dumps(_personal_payload()).encode())
    cid = _capture_id(sessions)
    r = TestClient(app).get(f"/captures/{cid}/report.json", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert "/login" in r.headers["location"]
