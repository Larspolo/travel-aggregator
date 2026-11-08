"""A test message from the messages settings page (#1086). A test double replaces the POST."""

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.main import app

from app import notify
from app.models import Setting
from tests.test_settings_page import PASSWORD, _token
from tests.test_settings_page import client as login_client  # noqa: F401  (a fixture)

URL = "https://ntfy.example/topic"
TITLE = "Test message from travel-aggregator"


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "post", lambda url, text, headers: calls.append((url, text, headers)))
    return calls


def _channel(sessions, channel):
    with sessions() as s:
        s.merge(Setting(key=notify.CHANNEL_KEY, value=channel))
        s.merge(Setting(key=notify.NTFY_URL_KEY, value=URL))
        s.commit()


def _send(client):
    return client.post("/settings/messages/test", data={"csrf_token": _token(client, "/settings/messages")})


def test_ntfy_gets_one_test_message(login_client, sessions, sent):  # noqa: F811
    _channel(sessions, "ntfy")
    r = _send(login_client)
    assert r.status_code == 200 and "Test message sent by ntfy" in r.text
    assert len(sent) == 1
    url, _, headers = sent[0]
    assert url == URL and headers["Title"] == TITLE and headers["Click"].endswith("/settings/messages")


def test_channel_none_sends_nothing(login_client, sessions, sent):  # noqa: F811
    _channel(sessions, "none")
    r = _send(login_client)
    assert "Select a channel first" in r.text and sent == []


def test_no_csrf_token_gets_403(login_client, sent):  # noqa: F811
    assert login_client.post("/settings/messages/test", data={}).status_code == 403 and sent == []


def test_no_login_goes_to_the_login_page(sessions, monkeypatch, sent):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    r = c.post("/settings/messages/test", data={"csrf_token": _token(c, "/login")}, follow_redirects=False)
    assert r.status_code in (302, 303) and "/login" in r.headers["location"] and sent == []
