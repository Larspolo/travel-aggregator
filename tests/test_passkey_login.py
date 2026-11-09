"""Log in with a stored passkey: no password and no one-time code (#1559)."""

import os
import re
import time

import pytest
from fastapi.testclient import TestClient
from webauthn.helpers import bytes_to_base64url

from app import totp
from app.auth import TOTP_SECRET, login_limiter, make_password_hash
from app.main import app
from app.models import LoginEvent, Passkey, Setting
from tests.passkey_device import Device

PASSWORD = "correct horse"
ORIGIN = "http://testserver"


@pytest.fixture
def client(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    monkeypatch.delenv("PASSKEY_ORIGIN", raising=False)
    login_limiter.reset()
    yield TestClient(app)
    login_limiter.reset()


def _csrf(client, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _password_login(client):
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(client, "/login")},
                    follow_redirects=False)
    assert r.status_code == 303
    return r


def _register(client, device):
    """Log in with the password, add DEVICE on the settings page, and log out."""
    _password_login(client)
    csrf = _csrf(client, "/settings")
    options = client.post("/settings/passkeys/options", headers={"X-CSRF-Token": csrf}).json()
    r = client.post("/settings/passkeys", json={"name": "Laptop", "credential": device.create(options, ORIGIN)},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    client.post("/logout")


def _passkey_login(client, device, **kwargs):
    csrf = _csrf(client, "/login")
    r = client.post("/login/passkey/options", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    return client.post("/login/passkey", json=device.get(r.json(), kwargs.pop("origin", ORIGIN), **kwargs),
                       headers={"X-CSRF-Token": csrf})


def _logged_in(client):
    return client.get("/", follow_redirects=False).status_code == 200


def _results(sessions):
    with sessions() as s:
        return [e.result for e in s.query(LoginEvent).order_by(LoginEvent.id)]


def test_the_login_page_shows_the_button_only_with_a_stored_passkey(client):
    assert "Log in with a passkey" not in client.get("/login").text
    _register(client, Device())
    assert "Log in with a passkey" in client.get("/login").text


def test_a_stored_passkey_logs_in_and_sets_the_last_use(client, sessions):
    device = Device()
    _register(client, device)
    r = _passkey_login(client, device)
    assert r.status_code == 200 and r.json() == {"next": "/"}
    assert _logged_in(client)
    with sessions() as s:
        row = s.query(Passkey).one()
        assert row.sign_count == 1 and row.last_used_at is not None
    assert _results(sessions)[-1] == "passkey"
    assert "login with passkey" in client.get("/settings").text


def test_the_passkey_skips_the_one_time_code(client, sessions):
    device = Device()
    _register(client, device)
    with sessions() as s:
        s.add(Setting(key=TOTP_SECRET, value=totp.new_secret()))
        s.commit()
    assert _passkey_login(client, device).status_code == 200
    assert _logged_in(client)


def test_a_removed_passkey_does_not_log_in(client, sessions):
    device = Device()
    _register(client, device)
    with sessions() as s:
        s.query(Passkey).delete()
        s.commit()
    r = _passkey_login(client, device)
    assert r.status_code == 401 and "not known here" in r.json()["error"]
    assert not _logged_in(client)
    assert _results(sessions)[-1] == "passkey-failed"


def test_an_unknown_credential_id_does_not_log_in(client, sessions):
    _register(client, Device())
    r = _passkey_login(client, Device())
    assert r.status_code == 401 and "not known here" in r.json()["error"]
    assert not _logged_in(client)
    assert _results(sessions)[-1] == "passkey-failed"


def test_a_wrong_challenge_does_not_log_in(client, sessions):
    device = Device()
    _register(client, device)
    r = _passkey_login(client, device, challenge=bytes_to_base64url(os.urandom(32)))
    assert r.status_code == 401 and "not correct" in r.json()["error"]
    assert not _logged_in(client)
    assert _results(sessions)[-1] == "passkey-failed"
    with sessions() as s:
        assert s.query(Passkey).one().last_used_at is None


def test_a_wrong_origin_does_not_log_in(client):
    device = Device()
    _register(client, device)
    r = _passkey_login(client, device, origin="https://evil.example")
    assert r.status_code == 401 and not _logged_in(client)


def test_a_replayed_answer_does_not_log_in(client):
    device = Device()
    _register(client, device)
    csrf = _csrf(client, "/login")
    options = client.post("/login/passkey/options", headers={"X-CSRF-Token": csrf}).json()
    answer = device.get(options, ORIGIN)
    assert client.post("/login/passkey", json=answer, headers={"X-CSRF-Token": csrf}).status_code == 200
    client.post("/logout")
    csrf = _csrf(client, "/login")
    client.post("/login/passkey/options", headers={"X-CSRF-Token": csrf})
    again = client.post("/login/passkey", json=answer, headers={"X-CSRF-Token": csrf})
    assert again.status_code == 401 and not _logged_in(client)


def test_the_rate_limit_applies_to_the_passkey_login(client):
    device = Device()
    _register(client, device)
    for _ in range(login_limiter.ADDRESS_MAX):
        assert _passkey_login(client, Device()).status_code == 401
    csrf = _csrf(client, "/login")
    r = client.post("/login/passkey/options", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 429 and "Too many attempts" in r.json()["error"]


def test_the_password_login_still_works_with_and_without_the_code(client, sessions):
    _register(client, Device())
    _password_login(client)
    assert _logged_in(client)
    client.post("/logout")
    secret = totp.new_secret()
    with sessions() as s:
        s.add(Setting(key=TOTP_SECRET, value=secret))
        s.commit()
    assert _password_login(client).headers["location"] == "/login/code"
    r = client.post("/login/code", data={"code": totp.code(secret, time.time()),
                                         "csrf_token": _csrf(client, "/login/code")}, follow_redirects=False)
    assert r.status_code == 303 and _logged_in(client)


def test_the_routes_need_the_csrf_token(client):
    assert client.post("/login/passkey/options").status_code == 403
    assert client.post("/login/passkey", json={}).status_code == 403
