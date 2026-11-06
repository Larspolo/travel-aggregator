"""The owner writes, changes and removes a note of an itinerary (#202): the note shows in the row, HTML in a note
shows as text (P5), an empty note removes it, and a note of more than 2000 characters gets 422."""

import re

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Itinerary, Trip
from tests.test_trip_page import ingest, offer


@pytest.fixture
def trip(sessions):
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(t)
        s.commit()
        trip_id = t.id
    app.dependency_overrides[require_login] = lambda: None
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {token}"}
    ingest(client, auth, trip_id, [offer("89.90", "ICE 105")])
    yield client, trip_id
    app.dependency_overrides.pop(require_login, None)


def csrf(client, trip_id):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)


def note_url(trip_id, itinerary):
    return f"/trips/{trip_id}/itineraries/{itinerary}/note"


def _itinerary_id(sessions, trip_id):
    with sessions() as s:
        return s.query(Itinerary).filter_by(trip_id=trip_id).one().id


def _note(sessions, itinerary):
    with sessions() as s:
        return s.get(Itinerary, itinerary).note


def test_a_saved_note_shows_in_the_row_and_an_empty_note_removes_it(trip, sessions):
    client, trip_id = trip
    it = _itinerary_id(sessions, trip_id)
    token = csrf(client, trip_id)
    r = client.post(note_url(trip_id, it), data={"csrf_token": token, "note": "  met Anna  "},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{trip_id}"
    assert _note(sessions, it) == "met Anna"
    assert '<div class="muted">met Anna</div>' in client.get(f"/trips/{trip_id}").text

    client.post(note_url(trip_id, it), data={"csrf_token": token, "note": "   "}, follow_redirects=False)
    assert _note(sessions, it) is None
    assert "met Anna" not in client.get(f"/trips/{trip_id}").text


def test_html_in_a_note_shows_as_text(trip, sessions):
    client, trip_id = trip
    it = _itinerary_id(sessions, trip_id)
    token = csrf(client, trip_id)
    client.post(note_url(trip_id, it), data={"csrf_token": token, "note": "<script>alert(1)</script>"},
                follow_redirects=False)
    page = client.get(f"/trips/{trip_id}").text
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_a_note_of_2001_characters_gets_422_and_changes_nothing(trip, sessions):
    client, trip_id = trip
    it = _itinerary_id(sessions, trip_id)
    token = csrf(client, trip_id)
    r = client.post(note_url(trip_id, it), data={"csrf_token": token, "note": "x" * 2001},
                    follow_redirects=False)
    assert r.status_code == 422
    assert _note(sessions, it) is None


def test_a_post_without_the_csrf_token_gets_403(trip, sessions):
    client, trip_id = trip
    it = _itinerary_id(sessions, trip_id)
    csrf(client, trip_id)
    r = client.post(note_url(trip_id, it), data={"note": "x"}, follow_redirects=False)
    assert r.status_code == 403
    assert _note(sessions, it) is None
