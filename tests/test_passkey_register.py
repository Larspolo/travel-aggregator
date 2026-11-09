"""Store a passkey on the settings page, list it and remove it (#1558).

A small software authenticator in this file makes the registration response ("none" attestation, ES256 key).
"""

import hashlib
import json
import os
import re

import cbor2
import pytest
from alembic import command
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from app.auth import make_password_hash
from app.main import app
from app.models import Passkey
from tests.test_trip_booked import _alembic

PASSWORD = "correct horse"
ORIGIN = "http://testserver"


@pytest.fixture
def client(monkeypatch, sessions):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    monkeypatch.delenv("PASSKEY_ORIGIN", raising=False)
    c = TestClient(app)
    r = c.post("/login", data={"password": PASSWORD, "csrf_token": _csrf(c, "/login")}, follow_redirects=False)
    assert r.status_code == 303
    return c


def _csrf(client, path="/settings"):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text).group(1)


def _credential(options, credential_id=None, origin=ORIGIN, challenge=None):
    """The answer of navigator.credentials.create() to OPTIONS, as PublicKeyCredential.toJSON() gives it."""
    credential_id = credential_id or os.urandom(16)
    key = ec.generate_private_key(ec.SECP256R1()).public_key().public_numbers()
    cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: key.x.to_bytes(32, "big"), -3: key.y.to_bytes(32, "big")})
    auth_data = (hashlib.sha256(options["rp"]["id"].encode()).digest() + bytes([0x45]) + (0).to_bytes(4, "big")
                 + bytes(16) + len(credential_id).to_bytes(2, "big") + credential_id + cose)
    client_data = json.dumps({"type": "webauthn.create", "challenge": challenge or options["challenge"],
                              "origin": origin, "crossOrigin": False}).encode()
    attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
    raw_id = bytes_to_base64url(credential_id)
    return {"id": raw_id, "rawId": raw_id, "type": "public-key", "clientExtensionResults": {},
            "response": {"clientDataJSON": bytes_to_base64url(client_data),
                         "attestationObject": bytes_to_base64url(attestation)}}


def _options(client, csrf):
    r = client.post("/settings/passkeys/options", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    return r.json()


def _add(client, name="Laptop", **kwargs):
    csrf = _csrf(client)
    credential = _credential(_options(client, csrf), **kwargs)
    return client.post("/settings/passkeys", json={"name": name, "credential": credential},
                       headers={"X-CSRF-Token": csrf})


def _rows(sessions):
    with sessions() as s:
        return [(p.name, p.last_used_at) for p in s.query(Passkey).all()]


def test_the_options_name_the_host_and_exclude_the_stored_passkeys(client):
    csrf = _csrf(client)
    options = _options(client, csrf)
    assert options["rp"]["id"] == "testserver" and options["excludeCredentials"] == []
    assert _add(client, credential_id=b"k" * 16).status_code == 200
    options = _options(client, csrf)
    assert [base64url_to_bytes(c["id"]) for c in options["excludeCredentials"]] == [b"k" * 16]


def test_a_correct_registration_is_listed_as_never_used(client, sessions):
    r = _add(client)
    assert r.status_code == 200, r.text
    assert _rows(sessions) == [("Laptop", None)]
    page = client.get("/settings").text
    card = page[page.index('id="passkeys"'):]
    assert 'class="passkey-name">Laptop<' in card and "never used" in card
    assert "The passkey “Laptop” is added." in page


def test_a_wrong_challenge_is_rejected(client, sessions):
    r = _add(client, challenge=bytes_to_base64url(os.urandom(32)))
    assert r.status_code == 400 and "not correct" in r.json()["error"]
    assert _rows(sessions) == []


def test_a_wrong_origin_is_rejected(client, sessions):
    r = _add(client, origin="https://evil.example")
    assert r.status_code == 400 and "not correct" in r.json()["error"]
    assert _rows(sessions) == []


def test_a_challenge_works_one_time_only(client, sessions):
    csrf = _csrf(client)
    credential = _credential(_options(client, csrf))
    body = {"name": "Laptop", "credential": credential}
    assert client.post("/settings/passkeys", json=body, headers={"X-CSRF-Token": csrf}).status_code == 200
    again = client.post("/settings/passkeys", json=body, headers={"X-CSRF-Token": csrf})
    assert again.status_code == 400 and "too old" in again.json()["error"]
    assert len(_rows(sessions)) == 1


def test_the_same_credential_id_is_not_stored_twice(client, sessions):
    assert _add(client, credential_id=b"same-id-12345678").status_code == 200
    r = _add(client, name="Phone", credential_id=b"same-id-12345678")
    assert r.status_code == 400 and "already added" in r.json()["error"]
    assert _rows(sessions) == [("Laptop", None)]


def test_a_blank_name_is_rejected(client, sessions):
    r = _add(client, name="  ")
    assert r.status_code == 400 and "name" in r.json()["error"]
    assert _rows(sessions) == []


def test_passkey_origin_overrides_the_request(client, monkeypatch):
    monkeypatch.setenv("PASSKEY_ORIGIN", "https://travel.example.com/")
    assert _options(client, _csrf(client))["rp"]["id"] == "travel.example.com"
    assert _add(client).status_code == 400
    assert _add(client, origin="https://travel.example.com").status_code == 200


def test_remove_deletes_the_passkey(client, sessions):
    assert _add(client).status_code == 200
    with sessions() as s:
        pid = s.query(Passkey).one().id
    r = client.post(f"/settings/passkeys/{pid}/delete", data={"csrf_token": _csrf(client)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/settings#passkeys"
    assert _rows(sessions) == []
    assert "No passkeys yet." in client.get("/settings").text


def test_the_routes_need_the_csrf_token(client):
    assert client.post("/settings/passkeys/options").status_code == 403
    assert client.post("/settings/passkeys", json={"name": "x", "credential": {}}).status_code == 403


def test_migration_0032_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        assert "passkeys" in inspect(engine).get_table_names()
        command.downgrade(cfg, "0031")
        assert "passkeys" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
