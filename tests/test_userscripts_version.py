"""The served @version of a .user.js file ends with CORE_VERSION of core.js (#391): Tampermonkey updates a script
when core.js changes, because the served version grows."""

import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.web.userscripts as userscripts
from app.main import app

GUARDS = ("userscripts/*", "tests/data/userscript_versions.json")   # ship_pr runs this file for these changes
DIR = Path(__file__).resolve().parents[1] / "userscripts"
SERVER = "https://travel.example"
VERSION = re.compile(r"^// @version[ \t]+(\S+)[ \t]*$", re.MULTILINE)


def served_version(client, name: str) -> str:
    m = VERSION.search(client.get(f"/userscripts/{name}").text)
    assert m, "no @version line in the served script"
    return m.group(1)


def parts(version: str) -> list[int]:
    return [int(p) for p in version.split(".")]


@pytest.fixture
def client():
    return TestClient(app, base_url=SERVER)


def test_served_version_is_file_version_and_core_version(client):
    file_version = VERSION.search((DIR / "bahn.user.js").read_text(encoding="utf-8")).group(1)
    core_version = userscripts.core_version((DIR / "core.js").read_text(encoding="utf-8"))
    assert served_version(client, "bahn.user.js") == f"{file_version}.{core_version}"


def test_core_version_is_an_integer_in_core_js():
    text = (DIR / "core.js").read_text(encoding="utf-8")
    assert re.search(r"^const CORE_VERSION = \d+;", text, re.MULTILINE)


def test_higher_core_version_gives_higher_served_version(client, tmp_path, monkeypatch):
    # A temporary copy of userscripts/ with a higher CORE_VERSION: the served version must grow.
    copy = tmp_path / "userscripts"
    shutil.copytree(DIR, copy)
    core = copy / "core.js"
    old = served_version(client, "bahn.user.js")
    core.write_text(
        re.sub(r"^const CORE_VERSION = \d+;",
               lambda m: "const CORE_VERSION = 99;",
               core.read_text(encoding="utf-8"), count=1, flags=re.MULTILINE),
        encoding="utf-8",
    )
    monkeypatch.setattr(userscripts, "USERSCRIPTS_DIR", copy)
    new = served_version(client, "bahn.user.js")
    assert new != old
    assert parts(new) > parts(old)
    assert new.endswith(".99")
