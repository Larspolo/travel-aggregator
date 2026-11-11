"""`python3 -m app.totp off`: the emergency switch of the second login step, run in the container (#1318)."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth import SESSION_EPOCH, TOTP_SECRET, TOTP_STEP, make_password_hash
from app.main import app
from app.models import Setting
from app.totp import OFF_LINE

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "correct horse"


def _run(database_url, *args):
    env = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run([sys.executable, "-m", "app.totp", *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=120)


def _settings(sessions):
    with sessions() as s:
        return {row.key: row.value for row in s.query(Setting).all()}


def _put(sessions, values):
    with sessions() as s:
        for key, value in values.items():
            s.merge(Setting(key=key, value=value))
        s.commit()


def test_off_with_the_step_on_deletes_the_rows_and_ends_the_sessions(migrated_url, sessions):
    _put(sessions, {TOTP_SECRET: "JBSWY3DPEHPK3PXP", TOTP_STEP: "123", SESSION_EPOCH: "3"})

    r = _run(migrated_url, "off")

    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == OFF_LINE
    assert _settings(sessions) == {SESSION_EPOCH: "4"}


def test_password_alone_logs_in_after_the_off_command(migrated_url, sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    _put(sessions, {TOTP_SECRET: "JBSWY3DPEHPK3PXP", TOTP_STEP: "-1"})
    assert _run(migrated_url, "off").returncode == 0

    client = TestClient(app)
    page = client.get("/login").text
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = client.post("/login", data={"password": PASSWORD, "csrf_token": token}, follow_redirects=False)

    assert r.status_code == 303
    assert r.headers["location"] != "/login"


def test_off_with_the_step_already_off_changes_nothing(migrated_url, sessions):
    _put(sessions, {SESSION_EPOCH: "7", "unrelated": "keep"})
    before = _settings(sessions)

    r = _run(migrated_url, "off")

    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == OFF_LINE
    assert _settings(sessions) == before


@pytest.mark.parametrize("args", [[], ["on"], ["off", "now"], ["OFF"]])
def test_wrong_argument_prints_the_usage_and_exits_2(migrated_url, sessions, args):
    _put(sessions, {TOTP_SECRET: "JBSWY3DPEHPK3PXP", SESSION_EPOCH: "1"})
    before = _settings(sessions)

    r = _run(migrated_url, *args)

    assert r.returncode == 2
    assert "usage: python3 -m app.totp off" in r.stderr
    assert _settings(sessions) == before
