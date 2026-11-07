"""Each page extends base.html (#311)."""

import re

from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Trip

PASSWORD = "pw"
STYLE = "--line: #8884"


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def test_pages_have_base_style(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    login = c.get("/login").text
    assert STYLE in login and 'name="viewport"' in login
    assert 'href="/settings"' not in login
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    with sessions() as s:
        trip = Trip(title="T")
        s.add(trip)
        s.commit()
        tid = trip.id
    for path in ["/", "/trips/new", f"/trips/{tid}/edit", f"/trips/{tid}/offers/new", "/tokens", "/sources/new"]:
        r = c.get(path)
        assert r.status_code == 200, path
        assert STYLE in r.text and r.text.count("<html") == 1, path
