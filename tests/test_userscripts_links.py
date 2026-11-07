"""The tokens page shows an install link for each userscript (#390)."""

import re

import pytest
from fastapi.testclient import TestClient

import app.web.userscripts as userscripts
from app.auth import make_password_hash
from app.main import app

PASSWORD = "pw"


@pytest.fixture
def client(sessions, monkeypatch):
    monkeypatch.setenv("OWNER_PASSWORD_HASH", make_password_hash(PASSWORD, iterations=1000))
    c = TestClient(app)
    token = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").text).group(1)
    c.post("/login", data={"password": PASSWORD, "csrf_token": token})
    return c


def test_one_line_per_userscript(client):
    page = client.get("/tokens").text
    files = sorted(p.name for p in userscripts.USERSCRIPTS_DIR.glob("*.user.js"))
    assert files
    for s in userscripts.userscript_list():
        served = client.get(f"/userscripts/{s['file']}").text
        assert f"// @version      {s['version']}" in served
        assert f"// @name         {s['name']}" in served
        assert f'<a href="/userscripts/{s["file"]}">Install</a>' in page
        assert f"{s['name']} {s['version']}" in page
    assert [s["file"] for s in userscripts.userscript_list()] == files


def test_list_follows_directory(client, tmp_path, monkeypatch):
    (tmp_path / "core.js").write_text("const CORE_VERSION = 7;\n")
    (tmp_path / "x.user.js").write_text("// ==UserScript==\n// @name         X site\n// @version      2.1\n"
                                        "// ==/UserScript==\n")
    monkeypatch.setattr(userscripts, "USERSCRIPTS_DIR", tmp_path)
    assert userscripts.userscript_list() == [{"file": "x.user.js", "name": "X site", "version": "2.1.7"}]
    page = client.get("/tokens").text
    assert "X site 2.1.7" in page and 'href="/userscripts/x.user.js"' in page
