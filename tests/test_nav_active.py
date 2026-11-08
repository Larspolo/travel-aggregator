"""The top bar links all main pages and marks the current page (#619); all settings pages mark "Settings" (#925)."""

import re

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


@pytest.mark.parametrize("path,marked", [("/", "/"), ("/upcoming", "/upcoming"), ("/captures", "/captures"),
                                         ("/settings", "/settings"), ("/settings/messages", "/settings"),
                                         ("/profiles", "/settings"), ("/places", "/settings"),
                                         ("/rates", "/settings"), ("/tokens", "/settings"),
                                         ("/sources/new", "/settings")])
def test_current_page_is_marked(client, path, marked):
    html = client.get(path).text
    for href in ["/", "/upcoming", "/captures", "/settings", "/logout"]:
        assert f'href="{href}"' in html
    active = re.findall(r'<a href="([^"]+)" class="active" aria-current="page">', html)
    assert active == [marked]
