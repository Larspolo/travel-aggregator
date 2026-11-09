"""End the other login sessions from the settings page (#1266)."""

import re

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import LoginRequired, make_password_hash, require_login
from app.main import app
from app.models import Trip

PASSWORD = "correct horse"


@pytest.fixture
def setup(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="A – B", origin_text="A", destination_text="B")
        s.add(t)
        s.commit()
    return {"Authorization": f"Bearer {token}"}


def _csrf(client, path="/login"):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _login(client):
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(client)}, follow_redirects=False)
    assert r.status_code == 303


def _end_others(client):
    return client.post("/settings/sessions/end-others", data={"csrf_token": _csrf(client, "/settings")},
                       follow_redirects=False)


def test_the_post_logs_out_the_other_client_only(setup):
    one, two = TestClient(app), TestClient(app)
    _login(one)
    _login(two)
    assert two.get("/", follow_redirects=False).status_code == 200
    r = _end_others(one)
    assert r.status_code == 303 and r.headers["location"] == "/settings"
    assert "All other devices are logged out." in one.get("/settings").text
    assert one.get("/", follow_redirects=False).status_code == 200
    r = two.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    _login(two)
    assert two.get("/", follow_redirects=False).status_code == 200


def test_the_settings_page_has_the_card(setup):
    client = TestClient(app)
    _login(client)
    page = client.get("/settings").text
    assert "Sessions" in page and "Log out on all other devices" in page and "confirm(" not in page


def test_api_token_and_share_link_still_work(setup):
    client = TestClient(app)
    _login(client)
    assert _end_others(client).status_code == 303
    assert TestClient(app).get("/api/trips", headers=setup).status_code == 200
    trip_id = client.get("/api/trips", headers=setup).json()[0]["id"]
    csrf = _csrf(client, f"/trips/{trip_id}")
    r = client.post(f"/trips/{trip_id}/share", data={"csrf_token": csrf})
    link = re.search(r'<pre class="share-link">([^<]+)</pre>', r.text).group(1).removeprefix("http://testserver")
    assert _end_others(client).status_code == 303
    assert TestClient(app).get(link).status_code == 200


def test_a_post_with_no_csrf_token_gives_403(setup):
    client = TestClient(app)
    _login(client)
    assert client.post("/settings/sessions/end-others", follow_redirects=False).status_code == 403


class _Request:
    def __init__(self, data):
        self.session = data


def test_a_session_with_no_epoch_works_at_epoch_0(sessions):
    with sessions() as s:
        require_login(_Request({"owner": True}), s)
        data = {"owner": True, "epoch": 1}
        with pytest.raises(LoginRequired):
            require_login(_Request(data), s)
        assert data == {}
