"""The end date of an API token on the tokens page (#1847)."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import tokens
from app.auth import make_password_hash
from app.main import app
from app.models import ApiToken

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _create(c, name="laptop", expires_on=""):
    return c.post("/tokens", data={"name": name, "expires_on": expires_on, "csrf_token": _token(c, "/tokens")})


def _today():
    return datetime.now(UTC).date()


def test_token_with_end_date_shows_that_date(sessions, client):
    last_day = _today() + timedelta(days=30)
    r = _create(client, expires_on=last_day.isoformat())
    assert r.status_code == 200
    page = client.get("/tokens").text
    assert f"<td>{last_day.isoformat()}</td>" in page
    with sessions() as s:
        t = s.scalars(select(ApiToken)).one()
        assert t.expires_at == datetime.combine(last_day + timedelta(days=1), datetime.min.time(), tzinfo=UTC)


def test_token_without_end_date_shows_never(sessions, client):
    _create(client, expires_on="")
    with sessions() as s:
        assert s.scalars(select(ApiToken)).one().expires_at is None
    page = client.get("/tokens").text
    assert "<th>Ends</th>" in page
    assert re.search(r"<td>never</td>", page)


def test_past_date_gives_error_and_makes_no_token(sessions, client):
    past = (_today() - timedelta(days=1)).isoformat()
    r = _create(client, expires_on=past)
    assert r.status_code == 422
    assert "The end date is before today. No token was made." in r.text
    with sessions() as s:
        assert s.scalars(select(ApiToken)).all() == []


def test_bad_date_gives_error_and_makes_no_token(sessions, client):
    r = _create(client, expires_on="31/12/2030")
    assert r.status_code == 422
    assert "The end date is not a valid date." in r.text
    with sessions() as s:
        assert s.scalars(select(ApiToken)).all() == []


def test_token_after_its_end_date_shows_ended(sessions, client):
    with sessions() as s:
        s.add(ApiToken(name="old", token_hash="x" * 64,
                       expires_at=datetime.now(UTC) - timedelta(hours=1)))
        s.commit()
    page = client.get("/tokens").text
    assert '<span class="chip">ended</span>' in page


def test_token_before_its_end_date_is_not_ended(sessions, client):
    _create(client, expires_on=(_today() + timedelta(days=5)).isoformat())
    assert '<span class="chip">ended</span>' not in client.get("/tokens").text


def test_create_token_helper_stores_end_date(sessions):
    end = datetime(2030, 1, 2, tzinfo=UTC)
    with sessions() as s:
        tokens.create(s, "phone", expires_at=end)
        assert s.scalars(select(ApiToken)).one().expires_at == end
