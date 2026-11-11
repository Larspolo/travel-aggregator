"""The delete of a capture with a confirm page (#2187): the link on the captures page, the counts, the CSRF check."""

import re

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import make_password_hash
from app.capture_delete import delete_counts
from app.main import app
from app.models import Capture, FarePrice, Trip
from tests.test_ingest_api import body

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        token = tokens.create(s, "test")
        trip = Trip(title="Reise")
        s.add(trip)
        s.commit()
        trip_id = trip.id
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c, "/login")})
    return c, {"Authorization": f"Bearer {token}"}, trip_id


def _csrf(c, path):
    return re.search(r'csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _ingest(c, auth, trip_id, sessions, **kw):
    assert c.post("/api/ingest", headers=auth, json=body(trip_id, **kw)).status_code == 200
    with sessions() as s:
        return s.query(Capture).order_by(Capture.id.desc()).first().id


def test_captures_page_links_each_capture_to_its_delete_page(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions, raw={"a": 1})
    text = c.get(f"/trips/{trip_id}/captures").text
    assert f'href="/captures/{cid}/delete"' in text
    assert re.search(rf'<a class="delete-capture" href="/captures/{cid}/delete">Delete</a>', text)


def test_confirm_page_shows_the_counts_and_a_delete_button(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions, raw={"a": 1})
    with sessions() as s:
        expected = delete_counts(s, s.get(Capture, cid))
    text = c.get(f"/captures/{cid}/delete").text
    assert f'action="/captures/{cid}/delete"' in text
    assert "Delete</button>" in text
    assert "This cannot be undone." in text
    assert f"with {expected['prices']} price rows?" in text
    assert f"{expected['itineraries']} itineraries and {expected['fares']} fares" in text


def test_post_without_csrf_token_gives_403_and_keeps_the_capture(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions, raw={"a": 1})
    r = c.post(f"/captures/{cid}/delete", follow_redirects=False)
    assert r.status_code == 403
    with sessions() as s:
        assert s.get(Capture, cid) is not None


def test_post_with_csrf_token_deletes_the_capture_and_its_prices(client, sessions):
    c, auth, trip_id = client
    cid = _ingest(c, auth, trip_id, sessions, raw={"a": 1})
    with sessions() as s:
        prices_before = s.query(FarePrice).filter_by(capture_id=cid).count()
        assert prices_before > 0
    r = c.post(f"/captures/{cid}/delete", data={"csrf_token": _csrf(c, f"/captures/{cid}/delete")},
               follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/trips/{trip_id}/captures"
    with sessions() as s:
        assert s.get(Capture, cid) is None
        assert s.query(FarePrice).filter_by(capture_id=cid).count() == 0


def test_unknown_capture_gives_404(client):
    c, _, _ = client
    assert c.get("/captures/999999/delete").status_code == 404
    r = c.post("/captures/999999/delete", data={"csrf_token": _csrf(c, "/login")}, follow_redirects=False)
    assert r.status_code == 404
