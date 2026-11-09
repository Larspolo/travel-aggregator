"""The settings page shows the result of the check of the newest backup (#1491). The setting is written by the daily loop (#1490)."""

import json
import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.auth import make_password_hash
from app.backup import STAMP_FORMAT
from app.main import app
from app.models import Setting

PASSWORD = "pw"
WHEN = datetime(2026, 11, 8, 3, 0, tzinfo=UTC)
NAME = f"{WHEN.strftime(STAMP_FORMAT)}-daily.dump"


@pytest.fixture
def client(sessions, monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    (tmp_path / "bk").mkdir()
    (tmp_path / "bk" / NAME).write_bytes(b"x" * 100)
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def _set(sessions, value):
    with sessions() as s:
        s.merge(Setting(key="backup_check", value=value))
        s.commit()


def test_ok_check_of_newest_file_shows_tables(client, sessions):
    _set(sessions, json.dumps({"file": NAME, "tables": 12, "at": "2026-11-08T03:00:05Z"}))
    html = client.get("/settings").text
    assert "Checked: 12 tables" in html
    assert 'class="chip good backup-check"' in html


def test_failed_check_shows_alert(client, sessions):
    _set(sessions, json.dumps({"file": NAME, "error": "pg_restore: <bad> toc", "at": "2026-11-08T03:00:05Z"}))
    html = client.get("/settings").text
    assert re.search(r'<p role="alert" class="chip warn backup-check">Check failed at 2026-11-08T03:00:05Z UTC: ', html)
    assert "&lt;bad&gt;" in html and "<bad>" not in html


def test_no_setting_shows_not_checked(client):
    html = client.get("/settings").text
    assert "Not checked yet" in html and 'class="chip backup-check"' in html
    assert "Checked:" not in html and "Check failed" not in html


def test_check_of_another_file_shows_not_checked(client, sessions):
    _set(sessions, json.dumps({"file": "20260101T000000Z-daily.dump", "tables": 12, "at": "2026-01-01T00:00:05Z"}))
    html = client.get("/settings").text
    assert "Not checked yet" in html and "Checked:" not in html


def test_broken_value_shows_not_checked(client, sessions):
    _set(sessions, "{not json")
    r = client.get("/settings")
    assert r.status_code == 200 and "Not checked yet" in r.text
