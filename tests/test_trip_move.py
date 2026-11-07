"""The move of a trip by its JSON export and its import, end to end (#778): the export of a trip with offers from 2
sources, the delete of the trip, the import as a new trip, and a second import that adds no row."""

import copy
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import Fare, FarePrice, Itinerary, Trip
from app.web.export import load_trip, trip_export
from tests.test_ingest_api import BODY
from tests.test_trip_page import offer

PASSWORD = "pw"


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    with sessions() as s:
        token = tokens.create(s, "test")
        s.commit()
    return c, {"Authorization": f"Bearer {token}"}


def _ingest(c, auth, trip_id, source, captured_at, offers):
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, source=source, captured_at=captured_at, offers=offers)
    r = c.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text


def _export(sessions, trip_id):
    with sessions() as s:
        return trip_export(load_trip(s, trip_id))


def _strip(data):
    data = copy.deepcopy(data)
    data.pop("exported_at")
    data["trip"].pop("id")
    for it in data["itineraries"]:
        it.pop("id")
    return data


def _counts(sessions):
    with sessions() as s:
        return tuple(s.scalar(select(func.count()).select_from(m)) for m in (Itinerary, Fare, FarePrice))


def _delete(c, trip_id):
    r = c.post(f"/trips/{trip_id}/delete", data={"csrf_token": _token(c, f"/trips/{trip_id}/delete")},
               follow_redirects=False)
    assert r.status_code == 303


def _import(c, data, target=""):
    return c.post("/trips/import", data={"csrf_token": _token(c, "/trips/import"), "target": target},
                  files={"file": ("export.json", data, "application/json")}, follow_redirects=False)


def test_a_trip_moves_by_export_and_import_with_the_same_rows_and_no_duplicate(client, sessions):
    c, auth = client
    with sessions() as s:
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        tid = t.id
    # Two captures of one fare from bahn.de (two price rows), and one offer from a second source.
    _ingest(c, auth, tid, "bahn.de", "2026-11-03T19:41:00Z", [offer("89.90")])
    _ingest(c, auth, tid, "bahn.de", "2026-11-04T08:00:00Z", [offer("79.90")])
    _ingest(c, auth, tid, "nsinternational.com", "2026-11-04T09:00:00Z", [offer("99.00")])
    before = _export(sessions, tid)
    assert len(before["itineraries"]) == 1 and len(before["itineraries"][0]["fares"]) == 2

    # 1 and 2: the download of the export.
    data = c.get(f"/trips/{tid}/export.json").content

    # 3: the delete of the trip leaves no copy in the database.
    _delete(c, tid)
    with sessions() as s:
        assert s.get(Trip, tid) is None

    # 4 and 5: the import as a new trip gives the same export, except the ids and the time of the export.
    r = _import(c, data)
    assert r.status_code == 303
    new_id = int(r.headers["location"].rsplit("/", 1)[1])
    assert new_id != tid
    assert _strip(_export(sessions, new_id)) == _strip(before)

    # 6: a second import into the preselected trip adds no row.
    counts = _counts(sessions)
    r2 = _import(c, data, target=str(new_id))
    assert r2.status_code == 303
    assert _counts(sessions) == counts
