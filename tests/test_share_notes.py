"""The optional note of the travel partner on a "Suits me" mark of the read-only link (#1782, epic #1780)."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Itinerary, ShareMark
from tests.test_share import _setup, share
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)


def _rows(sessions, trip_id):
    with sessions() as s:
        return {i.legs[0].service_no: i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id))}


def _notes(sessions, trip_id):
    with sessions() as s:
        return {m.itinerary_id: m.note for m in s.scalars(select(ShareMark).where(ShareMark.trip_id == trip_id))}


def test_a_note_shows_on_the_read_only_page(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    rows = _rows(sessions, trip_id)
    link = share(client, trip_id)
    anon = TestClient(app)  # the travel partner: no login, no CSRF token
    r = anon.post(f"{link}/marks/{rows['ICE 105']}", data={"note": "Fine, but not before 08:00"},
                  follow_redirects=False)
    assert r.status_code == 303
    assert _notes(sessions, trip_id) == {rows["ICE 105"]: "Fine, but not before 08:00"}
    page = anon.get(link).text
    assert "Fine, but not before 08:00" in page


def test_a_note_of_201_characters_gives_422_and_stores_nothing(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    rows = _rows(sessions, trip_id)
    link = share(client, trip_id)
    anon = TestClient(app)
    r = anon.post(f"{link}/marks/{rows['ICE 105']}", data={"note": "x" * 201}, follow_redirects=False)
    assert r.status_code == 422
    assert "at most 200 characters" in r.text
    assert _notes(sessions, trip_id) == {}


def test_a_note_of_200_characters_is_kept(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    rows = _rows(sessions, trip_id)
    link = share(client, trip_id)
    anon = TestClient(app)
    r = anon.post(f"{link}/marks/{rows['ICE 105']}", data={"note": "x" * 200}, follow_redirects=False)
    assert r.status_code == 303
    assert _notes(sessions, trip_id) == {rows["ICE 105"]: "x" * 200}


def test_a_blank_note_stores_the_mark_with_no_note(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    rows = _rows(sessions, trip_id)
    link = share(client, trip_id)
    anon = TestClient(app)
    r = anon.post(f"{link}/marks/{rows['ICE 105']}", data={"note": "   "}, follow_redirects=False)
    assert r.status_code == 303
    assert _notes(sessions, trip_id) == {rows["ICE 105"]: None}


def test_a_script_in_a_note_shows_as_escaped_text(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    rows = _rows(sessions, trip_id)
    link = share(client, trip_id)
    anon = TestClient(app)
    anon.post(f"{link}/marks/{rows['ICE 105']}", data={"note": "<script>alert(1)</script>"})
    page = anon.get(link).text
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_save_note_changes_the_note_and_keeps_the_mark(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    rows = _rows(sessions, trip_id)
    link = share(client, trip_id)
    anon = TestClient(app)
    anon.post(f"{link}/marks/{rows['ICE 105']}", data={"note": "first"})
    anon.post(f"{link}/marks/{rows['ICE 105']}", data={"note": "second", "edit": "1"})
    assert _notes(sessions, trip_id) == {rows["ICE 105"]: "second"}
    anon.post(f"{link}/marks/{rows['ICE 105']}", data={"note": "", "edit": "1"})
    assert _notes(sessions, trip_id) == {rows["ICE 105"]: None}


def test_remove_deletes_the_mark_and_its_note(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _setup(client, auth, trip_id, sessions)
    rows = _rows(sessions, trip_id)
    link = share(client, trip_id)
    anon = TestClient(app)
    anon.post(f"{link}/marks/{rows['ICE 105']}", data={"note": "keep me? no"})
    anon.post(f"{link}/marks/{rows['ICE 105']}", data={"note": "keep me? no", "remove": "1"})
    assert _notes(sessions, trip_id) == {}
