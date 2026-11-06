"""API token auth (#5): only a valid, not revoked token passes; the database holds only the hash."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.auth import require_token
from app.db import get_session
from app.main import app as main_app
from app.models import ApiToken

probe = FastAPI()


@probe.get("/probe")
def _probe(token: ApiToken = Depends(require_token)) -> dict:
    return {"name": token.name}


@pytest.fixture
def client(sessions):
    probe.dependency_overrides[get_session] = main_app.dependency_overrides[get_session]
    yield TestClient(probe)
    probe.dependency_overrides.clear()


def test_a_valid_token_passes_and_is_marked_used(client, sessions):
    with sessions() as s:
        token = tokens.create(s, "laptop")
    r = client.get("/probe", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json() == {"name": "laptop"}
    with sessions() as s:
        assert s.scalar(select(ApiToken)).last_used_at is not None


@pytest.mark.parametrize("header", [None, "Bearer", "Bearer wrong-token", "Basic dXNlcjpwYXNz"])
def test_a_missing_or_wrong_token_gets_401(client, sessions, header):
    with sessions() as s:
        tokens.create(s, "laptop")
    r = client.get("/probe", headers={"Authorization": header} if header else {})
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_a_revoked_token_gets_401(client, sessions):
    with sessions() as s:
        token = tokens.create(s, "laptop")
        token_id = s.scalar(select(ApiToken.id))
        assert tokens.revoke(s, token_id)
        assert not tokens.revoke(s, token_id)
    assert client.get("/probe", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_the_database_holds_only_the_hash(sessions):
    with sessions() as s:
        token = tokens.create(s, "laptop")
        stored = s.scalar(select(ApiToken))
    assert token not in stored.token_hash and len(stored.token_hash) == 64


def test_the_command_prints_the_token_once(sessions, capsys):
    with sessions() as s:
        assert tokens.main(["create", "phone"], session=s) == 0
    token = capsys.readouterr().out.strip()
    with sessions() as s:
        assert tokens.main(["list"], session=s) == 0
        listed = capsys.readouterr().out
        assert "phone" in listed and "active" in listed and token not in listed
        assert tokens.main(["revoke", "99"], session=s) == 1
