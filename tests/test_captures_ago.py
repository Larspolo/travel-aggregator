"""The captures pages show the age of each capture, the full UTC time in the title (#669)."""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Trip

FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen-bahncard25.json"
PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Reise mit Alter")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c, "/login")})
    return c, {"Authorization": f"Bearer {token}"}, trip_id


def _csrf(c, path):
    return re.search(r'csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def test_captures_show_the_age_and_the_full_time(client):
    c, auth, trip_id = client
    captured = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(second=0, microsecond=0)
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    r = c.post("/api/ingest", headers=auth, json={"trip_id": trip_id, "source": "bahn.de", "parser_version": "0.0.1",
                                                  "captured_at": captured.isoformat(), "raw": raw})
    assert r.status_code < 300, r.text
    full = captured.strftime("%Y-%m-%d %H:%M")
    for path in ("/captures", f"/trips/{trip_id}/captures"):
        text = c.get(path).text
        assert "2 h ago" in text, path
        assert f'title="{full} UTC"' in text, path
        assert f'datetime="{captured.isoformat()}"' in text, path
