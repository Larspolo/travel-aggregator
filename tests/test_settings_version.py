"""The card "Version" of the settings page (#1738)."""

import re

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

from app.api.health import _built
from app.auth import make_password_hash
from app.main import app
from app.web.pages import version_card

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    c.post("/login", data={"password": PASSWORD, "csrf_token": _token(c, "/login")})
    return c


def _token(c, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).text).group(1)


def _build_time(monkeypatch, tmp_path):
    build = tmp_path / "BUILD_TIME"
    build.write_text("2026-11-10T03:00:00Z\n", encoding="utf-8")
    monkeypatch.setenv("BUILD_TIME_FILE", str(build))
    _built.cache_clear()


def test_version_card_names_commit_build_time_and_head(client, monkeypatch, tmp_path):
    _build_time(monkeypatch, tmp_path)
    monkeypatch.setenv("GIT_SHA", "abc1234")
    page = client.get("/settings").text
    assert "Version" in page
    assert "Commit" in page and "abc1234" in page
    assert "https://github.com/Larspolo/travel-aggregator/commit/abc1234" in page
    assert "built 2026-11-10 03:00 UTC" in page
    assert "migrations pending" not in page
    assert "(head)" in page
    health = TestClient(app).get("/api/health").json()
    assert health["commit"] == "abc1234" and health["built"] == "2026-11-10T03:00:00Z"
    _built.cache_clear()


def test_version_card_says_when_migrations_are_pending(sessions, migrated_url, monkeypatch, tmp_path):
    # The page itself cannot render with the schema one revision behind (the layout reads itineraries, pinned.py),
    # so this checks the card's data: the container runs the migrations before the app starts.
    _build_time(monkeypatch, tmp_path)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", migrated_url)
    cfg.attributes["configure_logger"] = False
    command.downgrade(cfg, "0036")
    with sessions() as s:
        card = version_card(s)
    assert card["pending"] is True
    head = ScriptDirectory.from_config(cfg).get_current_head()  # not a fixed name: each new migration moves it
    assert card["current"] == "0036" and card["head"] == head != "0036"
    _built.cache_clear()
