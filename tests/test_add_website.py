"""The "Add a website" page (#304)."""

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.web.sources import issue_url
from tests.test_manual_entry import _token

PASSWORD = "pw"


def test_issue_url_is_prefilled():
    url = urlparse(issue_url("www.flixbus.nl"))
    assert url.netloc == "github.com" and url.path.endswith("/issues/new")
    q = parse_qs(url.query)
    assert q["title"] == ["Add source www.flixbus.nl"]
    assert "HAR" in q["body"][0]


def test_page_needs_login():
    r = TestClient(app).get("/sources/new", follow_redirects=False)
    assert r.status_code in (303, 401)


def test_page_shows_steps_and_link(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    r = c.get("/sources/new", params={"site": "www.flixbus.nl"})
    assert r.status_code == 200
    assert "Save all as HAR" in r.text and "issues/new?title=Add+source+www.flixbus.nl" in r.text
