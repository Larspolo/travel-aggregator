"""GET /userscripts/<name> (#389): the app serves core.js and each *.user.js file with the server address in the header,
and no other name (no path traversal)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

GUARDS = ("userscripts/*", "tests/data/userscript_versions.json")   # ship_pr runs this file for these changes
DIR = Path(__file__).resolve().parents[1] / "userscripts"
SERVER = "https://travel.example"
USER_FILES = sorted(p.name for p in DIR.glob("*.user.js"))


@pytest.fixture
def client():
    # The proxy of deploy/ sets X-Forwarded-Proto; the test client gives the https address directly.
    return TestClient(app, base_url=SERVER)


def test_user_script_has_the_server_lines(client):
    r = client.get("/userscripts/bahn.user.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/javascript")
    assert f"// @require      {SERVER}/userscripts/core.js" in r.text
    assert f"// @updateURL    {SERVER}/userscripts/bahn.user.js" in r.text
    assert f"// @downloadURL  {SERVER}/userscripts/bahn.user.js" in r.text
    assert "raw.githubusercontent.com" not in r.text


def test_core_is_the_file_itself(client):
    r = client.get("/userscripts/core.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/javascript")
    assert r.text == (DIR / "core.js").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["x.js", "../app/main.py", "..%2Fapp%2Fmain.py", "missing.user.js"])
def test_other_names_are_not_found(client, name):
    assert client.get(f"/userscripts/{name}").status_code == 404


@pytest.mark.parametrize("name", USER_FILES)
def test_every_user_script_gets_the_three_server_lines(client, name):
    text = client.get(f"/userscripts/{name}").text
    assert f"// @require      {SERVER}/userscripts/core.js" in text
    assert f"// @updateURL    {SERVER}/userscripts/{name}" in text
    assert f"// @downloadURL  {SERVER}/userscripts/{name}" in text
    assert text.count("// @updateURL") == 1
    assert text.count("// @downloadURL") == 1


def test_files_of_the_directory_are_unchanged():
    # The install from the repository keeps the GitHub address (the served copy is only for the server).
    for name in USER_FILES:
        assert "raw.githubusercontent.com" in (DIR / name).read_text(encoding="utf-8")
