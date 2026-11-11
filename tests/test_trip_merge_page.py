"""The "Merge into" card of the edit page, its confirmation page and its POST (#1262)."""

import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Itinerary, Trip

PASSWORD = "correct horse"


def _at(day):
    return datetime(2026, 11, day, 10, tzinfo=UTC)


@pytest.fixture
def trips(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        a = Trip(title="Source", origin_text="Köln", destination_text="Basel")
        b = Trip(title="Amsterdam → Zürich", origin_text="Amsterdam", destination_text="Zürich",
                 status="archived")
        c = Trip(title="Target", origin_text="Wien", destination_text="Graz")
        s.add_all([a, b, c])
        s.flush()
        for i in range(3):
            s.add(Itinerary(trip_id=a.id, fingerprint=f"a{i}", depart_at=_at(20), arrive_at=_at(20),
                            duration_min=60, first_seen_at=_at(1), last_seen_at=_at(1)))
        s.add(Capture(trip_id=a.id, source="stub", captured_at=_at(3)))
        s.commit()
        return {"source": a.id, "archived": b.id, "target": c.id}


def _csrf(client, path="/login"):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _login(client):
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(client)}, follow_redirects=False)
    assert r.status_code == 303


def test_the_edit_page_lists_the_other_trips_but_not_itself(trips):
    client = TestClient(app)
    _login(client)
    page = client.get(f"/trips/{trips['source']}/edit").text
    assert "Merge into another trip" in page
    assert f'<option value="{trips["target"]}">Target' in page
    assert f'<option value="{trips["archived"]}">Amsterdam → Zürich (archived)' in page
    assert f'<option value="{trips["source"]}">' not in page
    assert page.index(f'value="{trips["target"]}"') < page.index(f'value="{trips["archived"]}"')


def test_the_confirmation_page_shows_the_counts_and_merge_moves_the_data(trips, sessions):
    client = TestClient(app)
    _login(client)
    target = trips["target"]
    page = client.get(f"/trips/{trips['source']}/merge?into={target}")
    assert page.status_code == 200
    assert "Move 3 itineraries and 1 captures into Target, then delete this trip." in page.text
    csrf = _csrf(client, f"/trips/{trips['source']}/edit")
    r = client.post(f"/trips/{trips['source']}/merge?into={target}", data={"csrf_token": csrf, "into": target},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{target}"
    with sessions() as s:
        assert s.get(Trip, trips["source"]) is None
        assert s.query(Itinerary).filter_by(trip_id=target).count() == 3
        assert s.query(Capture).filter_by(trip_id=target).count() == 1


def test_a_linked_trip_shows_the_reason_and_the_post_changes_nothing(trips, sessions):
    with sessions() as s:
        s.add(Trip(title="Part", split_of_id=trips["source"]))
        s.commit()
    client = TestClient(app)
    _login(client)
    page = client.get(f"/trips/{trips['source']}/edit").text
    assert "This trip is linked to another trip" in page
    assert "Merge…" not in page
    csrf = _csrf(client, f"/trips/{trips['source']}/edit")
    r = client.post(f"/trips/{trips['source']}/merge?into={trips['target']}",
                    data={"csrf_token": csrf, "into": str(trips["target"])}, follow_redirects=False)
    assert r.status_code == 400
    with sessions() as s:
        assert s.get(Trip, trips["source"]) is not None
        assert s.query(Itinerary).filter_by(trip_id=trips["source"]).count() == 3


def test_a_post_with_no_csrf_token_gives_403(trips):
    client = TestClient(app)
    _login(client)
    r = client.post(f"/trips/{trips['source']}/merge", data={"into": str(trips["target"])},
                    follow_redirects=False)
    assert r.status_code == 403


def test_an_unknown_trip_gives_404(trips):
    client = TestClient(app)
    _login(client)
    assert client.get(f"/trips/9999/merge?into={trips['target']}").status_code == 404
    assert client.get(f"/trips/{trips['source']}/merge?into=9999").status_code == 404


def test_a_blank_target_gives_400(trips):
    client = TestClient(app)
    _login(client)
    assert client.get(f"/trips/{trips['source']}/merge?into=").status_code == 400
