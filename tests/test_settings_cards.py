"""The settings pages are cards with fields, and the backup chip tells the truth (#630)."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.backup import STAMP_FORMAT
from app.main import app

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def _chip(html):
    return re.search(r'class="chip (\w+) backup-state"', html).group(1)


def _backup(tmp_path, age):
    d = tmp_path / "bk"
    d.mkdir(exist_ok=True)
    (d / f"{(datetime.now(UTC) - age).strftime(STAMP_FORMAT)}-daily.dump").write_bytes(b"x")


def test_backup_chip_warn_without_backup(client):
    assert _chip(client.get("/settings").text) == "warn"


def test_backup_chip_warn_for_old_and_good_for_recent(client, tmp_path):
    _backup(tmp_path, timedelta(days=3))
    assert _chip(client.get("/settings").text) == "warn"
    _backup(tmp_path, timedelta(hours=1))
    assert _chip(client.get("/settings").text) == "good"


@pytest.mark.parametrize("path,titles", [
    ("/settings", ["Captures", "Backups"]),
    ("/settings/messages", ["Channel", "Web Push"]),
    ("/rates", ["Add or change a rate", "Rates"]),
    ("/tokens", ["Userscripts", "Create a token", "Tokens"]),
])
def test_sections_are_cards_with_fields(client, path, titles):
    html = client.get(path).text
    for t in titles:
        assert re.search(r'<section class="card[^"]*">\s*(<div class="card-header">)?<h2>' + re.escape(t), html), t
    for label in re.findall(r"<label[^>]*>", html):
        assert "for=" in label
    assert '<div class="field' in html


def test_delete_is_icon_button_with_label(client):
    html = client.get("/rates").text
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    client.post("/rates", data={"code": "CHF", "rate": "1.07", "csrf_token": token})
    html = client.get("/rates").text
    assert 'class="btn btn-danger btn-icon"' in html and 'aria-label="Delete CHF"' in html
