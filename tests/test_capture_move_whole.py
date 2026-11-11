"""The whole feature of epic #578 through the web: a capture into the wrong trip gets the warning, and after
"Move to trip" its offers show only in the correct trip, with no warning (#581)."""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip
from app.parsers.kiwi import KiwiParser

FIX = Path(__file__).parent / "fixtures" / "kiwi.com" / "search-amsterdam-lisbon.json"
PASSWORD = "pw"
WARNING = "These offers do not match the trip"


def _csrf(c, path):
    groups = re.search(r'csrf_token" value="([^"]+)"|X-CSRF-Token": "([^"]+)"', c.get(path).text).group(1, 2)
    return next(t for t in groups if t)


def _setup(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    parsed = KiwiParser().parse(raw)
    assert parsed.errors == []
    day = parsed.offers[0].legs[0].depart_at.date()
    with sessions() as s:
        token = tokens.create(s, "test")
        zurich = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zurich", date_from=day)
        lisbon = Trip(title="Amsterdam – Lisbon", origin_text="Amsterdam", destination_text="Lisbon", date_from=day)
        s.add_all([zurich, lisbon])
        s.commit()
        ids = zurich.id, lisbon.id
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c, "/login")})
    return c, token, ids, parsed


def test_a_capture_moved_to_the_correct_trip_loses_the_warning(sessions, monkeypatch):
    c, token, (zurich, lisbon), parsed = _setup(sessions, monkeypatch)
    service_nos = [o.legs[0].service_no for o in parsed.offers]
    assert service_nos

    # 1. the Lisbon fixture into the Zürich trip: the API answers with the warning
    body = {"trip_id": zurich, "source": "kiwi.com", "parser_version": KiwiParser.version,
            "captured_at": "2026-11-07T08:00:00Z", "raw": json.loads(FIX.read_text(encoding="utf-8"))}
    r = c.post("/api/ingest", json=body, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["warning"] is not None
    assert WARNING in c.get(f"/trips/{zurich}/captures").text

    # 2. move the capture to the Lisbon trip
    with sessions() as s:
        cid = s.scalars(select(Capture).where(Capture.trip_id == zurich)).one().id
    r = c.post(f"/captures/{cid}/move", data={"trip_id": lisbon},
               headers={"X-CSRF-Token": _csrf(c, "/captures")})
    assert r.status_code == 200, r.text
    assert "Moved to Amsterdam – Lisbon" in r.text

    # 3. the Lisbon trip page shows the offers, the Zürich trip page shows none
    lisbon_page = c.get(f"/trips/{lisbon}").text
    for no in service_nos:
        assert no in lisbon_page, no
    zurich_page = c.get(f"/trips/{zurich}").text
    for no in service_nos:
        assert no not in zurich_page, no

    # 4. the captures pages: Lisbon shows the capture with no warning, Zürich does not list it
    lisbon_captures = c.get(f"/trips/{lisbon}/captures").text
    assert f"/captures/{cid}/move" in lisbon_captures
    assert WARNING not in lisbon_captures
    assert f"/captures/{cid}/move" not in c.get(f"/trips/{zurich}/captures").text
