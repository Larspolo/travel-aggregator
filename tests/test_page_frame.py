"""Each page has one app bar and one page header with its only <h1>, and no second link line (#625)."""

import re

from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app
from app.models import Trip

PASSWORD = "pw"
# The old link lines under the <h1> repeated two or more links of the app bar.
NAV_LINE = re.compile(r'<p>(?:[^<]*<a href="(?:/|/places|/settings|/logout|/profiles|/captures)">[^<]*</a>){2,}')


def test_each_page_has_one_h1_in_the_page_header_and_no_link_line(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    with sessions() as s:
        trip = Trip(title="T", origin_text="A", destination_text="B")
        s.add(trip)
        s.commit()
        tid = trip.id
    paths = ["/", "/?archived=1", f"/trips/{tid}", "/trips/new", f"/trips/{tid}/edit", f"/trips/{tid}/delete",
             f"/trips/{tid}/offers/new", "/sources/new", "/captures", f"/trips/{tid}/captures", "/profiles",
             "/places", "/settings", "/rates", "/tokens"]
    for path in paths:
        r = c.get(path)
        assert r.status_code == 200, path
        html = r.text
        assert html.count("<h1") == 1, path
        assert re.search(r'<header class="page-header">\s*<div>\s*(<a class="back"[^>]*>[^<]*</a>\s*)?<h1>', html), path
        assert not NAV_LINE.search(html), path
        assert '<details class="menu">' in html, path


def test_settings_links_its_sub_pages(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    toolbar = c.get("/settings").text.split('class="toolbar"')[1].split("</header>")[0]
    assert 'href="/tokens"' in toolbar and 'href="/rates"' in toolbar
