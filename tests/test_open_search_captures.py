"""The link "Open search" on each capture of the captures pages (#2079)."""

import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Capture, Trip
from app.web.pages import web_url

PASSWORD = "pw"
URL = "https://www.flixbus.de/search?departureCity=1"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        trip = Trip(title="Reise")
        s.add(trip)
        s.flush()
        for i, url in enumerate([URL, None, "javascript:alert(1)"]):
            s.add(Capture(trip_id=trip.id, source="flixbus.de", page_url=url,
                          captured_at=datetime(2026, 11, 1, 10, i, tzinfo=timezone.utc)))
        s.commit()
        trip_id = trip.id
    c = TestClient(app)
    token = re.search(r'csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c, trip_id


def _links(text):
    return re.findall(r'<a class="open-search" href="([^"]*)" target="_blank" rel="noopener noreferrer">Open search</a>', text)


@pytest.mark.parametrize("path", ["/trips/{}/captures", "/captures"])
def test_only_a_web_address_gets_open_search(client, path):
    c, trip_id = client
    r = c.get(path.format(trip_id))
    assert r.status_code == 200
    assert _links(r.text) == [URL.replace("&", "&amp;")]
    assert "javascript:" not in r.text


def test_web_url_rule():
    assert web_url(URL) == URL
    assert web_url("http://a.example/") == "http://a.example/"
    for bad in (None, "", "javascript:alert(1)", "data:text/html,x", "/relative"):
        assert web_url(bad) is None
