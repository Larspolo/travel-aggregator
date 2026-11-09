"""The gone fares through the ingest API: two bahn.de captures of one trip and day, then a third (#1388, epic #1384).

The recon fixture has one connection with six fares. The second capture is a copy with the fare
"Super Sparpreis, 2nd class" removed, so the connection stays in the span of the capture."""

import copy
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Trip

RECON = json.loads((Path(__file__).parent / "fixtures" / "bahn.de" / "recon-169.json").read_text(encoding="utf-8"))
GONE = "Super Sparpreis, 2nd class"
MARK = "not in the last bahn.de search"


def without_super_sparpreis_2nd():
    raw = copy.deepcopy(RECON)
    conn = raw["response"]["verbindungen"][0]
    conn["reiseAngebote"] = [a for a in conn["reiseAngebote"]
                             if not (a["name"] == "Super Sparpreis" and a["klasse"] == "KLASSE_2")]
    return raw


@pytest.fixture
def trip(sessions):
    """A client with the owner login, a token and an empty trip."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Gone flow Köln – München")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    yield TestClient(app), {"Authorization": f"Bearer {token}"}, trip_id
    app.dependency_overrides.pop(require_login, None)


def post(client, auth, trip_id, raw, hours_ago):
    at = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {"trip_id": trip_id, "source": "bahn.de", "parser_version": "1.0.0", "captured_at": at, "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["errors"] == []


def fare_lines(page):
    """The text of each `<div class="fare">` on the trip page, by fare name."""
    out = {}
    for block in page.split('<div class="fare">')[1:]:
        block = block[:block.index("</div>")]
        name = re.search(r"bahn\.de: ([^<]+)", block).group(1).strip()
        out[name] = block
    return out


def best_on_list(client, trip_id):
    html = client.get("/").text
    card = html[html.index(f'href="/trips/{trip_id}/edit"'):]
    return re.search(r'class="trip-best">Best <strong>([^<]+)</strong>', card).group(1)


def test_a_fare_that_the_next_search_did_not_show_is_marked(trip):
    client, auth, trip_id = trip
    post(client, auth, trip_id, RECON, hours_ago=3)
    lines = fare_lines(client.get(f"/trips/{trip_id}").text)
    assert len(lines) == 6 and not any(MARK in line for line in lines.values())
    assert best_on_list(client, trip_id) == "€56.99"

    post(client, auth, trip_id, without_super_sparpreis_2nd(), hours_ago=2)
    lines = fare_lines(client.get(f"/trips/{trip_id}").text)
    assert len(lines) == 6
    assert [name for name, line in lines.items() if MARK in line] == [GONE]
    assert f"{MARK}, 2 h ago" in lines[GONE]
    assert best_on_list(client, trip_id) == "€65.99"  # Sparpreis, 2nd class: the cheapest current fare

    post(client, auth, trip_id, RECON, hours_ago=1)
    page = client.get(f"/trips/{trip_id}").text
    assert MARK not in page
    assert best_on_list(client, trip_id) == "€56.99"
