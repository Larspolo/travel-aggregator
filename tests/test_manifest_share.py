"""The installed app is a share target: the manifest names the share path of #2104 (#2105)."""

import re

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app

PASSWORD = "pw"
LINK = "https://www.bahn.de/x"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    return TestClient(app)


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def test_manifest_names_the_share_target(client):
    target = client.get("/manifest.webmanifest").json()["share_target"]
    assert target == {"action": "/share", "method": "GET",
                      "params": {"title": "title", "text": "text", "url": "url"}}


def test_the_share_action_is_a_route_that_answers_a_get_with_login(client, sessions):
    action = client.get("/manifest.webmanifest").json()["share_target"]["action"]
    client.post("/login", data={"password": PASSWORD, "csrf_token": _token(client, "/login")})
    assert client.get(action).status_code == 200
    assert client.get(action + "?url=" + LINK).status_code == 200


def test_a_shared_link_without_login_goes_to_the_login_and_back_to_the_form(client, sessions):
    response = client.get("/share?url=" + LINK, follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers["location"].startswith("/login")

    client.get(response.headers["location"])  # the login page keeps the asked page (#2103)
    page = client.post("/login", data={"password": PASSWORD,
                                       "csrf_token": _token(client, response.headers["location"])},
                       follow_redirects=True).text
    assert LINK in page
