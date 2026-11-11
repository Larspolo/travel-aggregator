"""The owner adds and deletes place names on the settings page (#2217)."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import make_password_hash
from app.main import app
from app.models import PlaceName

PASSWORD = "pw"


def _csrf(html):
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


@pytest.fixture
def client(sessions, monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c.get("/login").text)})
    return c


def _add(client, city, name):
    token = _csrf(client.get("/settings").text)
    return client.post("/settings/place-names", data={"city": city, "name": name, "csrf_token": token})


def _rows(sessions):
    with sessions() as s:
        return [(r.city, r.name) for r in s.scalars(select(PlaceName))]


def test_add_shows_and_delete_removes(client, sessions):
    assert _add(client, " Paris ", " Parijs ").status_code == 200
    assert _rows(sessions) == [("Paris", "Parijs")]
    html = client.get("/settings").text
    row = re.search(r'<tr class="place-name-row"><td>Paris</td><td>Parijs</td>.*?/settings/place-names/(\d+)/delete.*?Delete',
                    html, re.S)
    assert row
    client.post(f"/settings/place-names/{row.group(1)}/delete", data={"csrf_token": _csrf(html)})
    assert _rows(sessions) == []
    assert "place-name-row" not in client.get("/settings").text


@pytest.mark.parametrize("name", ["  ", "x" * 61, "Wien", "wien"])
def test_bad_name_gives_message_and_no_row(client, sessions, name):
    html = _add(client, "Vienna", name).text
    assert 'class="chip warn place-error"' in html
    assert _rows(sessions) == []


def test_name_is_escaped(client):
    _add(client, "Lyon", "<b>Lion</b>")
    html = client.get("/settings").text
    assert "&lt;b&gt;Lion&lt;/b&gt;" in html and "<b>Lion</b>" not in html


def test_no_login_redirects(sessions):
    c = TestClient(app, follow_redirects=False)
    for url in ("/settings/place-names", "/settings/place-names/1/delete"):
        r = c.post(url, data={"city": "Paris", "name": "Parijs"})
        assert r.status_code in (302, 303) and "/login" in r.headers["location"]
    assert _rows(sessions) == []
