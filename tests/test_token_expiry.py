"""The end date of an API token (#1846): after `expires_at` the API answers 401."""

from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app import tokens
from app.auth import token_limiter
from app.main import app
from app.models import ApiToken


@pytest.fixture(autouse=True)
def _limiter():
    token_limiter.reset()
    yield
    token_limiter.reset()


def _token(sessions, expires_at):
    with sessions() as s:
        token = tokens.create(s, "t", expires_at=expires_at)
        row = s.query(ApiToken).filter_by(expires_at=expires_at).order_by(ApiToken.id.desc()).first()
        return token, row.id


def _ingest(token):
    return TestClient(app).post("/api/ingest", json={}, headers={"Authorization": f"Bearer {token}"})


def test_expired_token_is_401_and_not_used(sessions):
    token, tid = _token(sessions, datetime.now(UTC) - timedelta(minutes=1))
    r = _ingest(token)
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid or missing API token"
    with sessions() as s:
        assert s.get(ApiToken, tid).last_used_at is None


@pytest.mark.parametrize("expires_at", [datetime.now(UTC) + timedelta(days=1), None])
def test_future_or_no_end_date_works(sessions, expires_at):
    token, tid = _token(sessions, expires_at)
    assert _ingest(token).status_code != 401
    with sessions() as s:
        assert s.get(ApiToken, tid).last_used_at is not None


def test_migration_with_tokens(empty_database_url):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", empty_database_url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "0043")
    engine = create_engine(empty_database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO api_tokens (name, token_hash) VALUES ('a', 'h1')"))
        command.upgrade(cfg, "0044")
        with engine.begin() as conn:
            assert conn.execute(text("SELECT expires_at FROM api_tokens")).scalar() is None
        command.downgrade(cfg, "0043")
        with engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM api_tokens")).scalar() == 1
            cols = conn.execute(text("SELECT column_name FROM information_schema.columns "
                                     "WHERE table_name = 'api_tokens'")).scalars().all()
            assert "expires_at" not in cols
    finally:
        engine.dispose()
