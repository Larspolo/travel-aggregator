"""One userscript for all sites: the server makes `travel-aggregator.user.js` from core.js and each site file. A new
site file is in it with no new install, and each site part runs only on its own pages. Playwright serves all URLs
from the test, so no request goes to a travel site (P1)."""

import json
import os
import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.web.userscripts as userscripts
from app.main import app

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "userscripts"
SERVER = "https://travel.example"
URL = f"/userscripts/{userscripts.BUNDLE}"
HEADER = re.compile(r"^// ==UserScript==\n(.*?)^// ==/UserScript==\n", re.MULTILINE | re.DOTALL)


@pytest.fixture
def client():
    return TestClient(app, base_url=SERVER)


def header_lines(text: str, key: str) -> list[str]:
    head = HEADER.match(text).group(1)
    return re.findall(rf"^// @{key}[ \t]+(.+?)[ \t]*$", head, re.MULTILINE)


def test_bundle_has_each_site_and_core(client):
    r = client.get(URL)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/javascript")
    text = r.text
    assert header_lines(text, "name") == [userscripts.BUNDLE_NAME]
    assert header_lines(text, "updateURL") == [f"{SERVER}{URL}"]
    assert header_lines(text, "downloadURL") == [f"{SERVER}{URL}"]
    assert header_lines(text, "require") == []  # core.js is in the file
    assert header_lines(text, "run-at") == ["document-start"]
    assert "const CORE_VERSION =" in text
    matches = header_lines(text, "match")
    grants = header_lines(text, "grant")
    for path in sorted(DIR.glob("*.user.js")):
        site = path.read_text(encoding="utf-8")
        assert set(header_lines(site, "match")) <= set(matches), path.name
        assert set(header_lines(site, "grant")) <= set(grants), path.name
        assert f"// ---- {path.name} ----" in text
    assert len(matches) == len(set(matches))


def test_bundle_follows_directory(client, tmp_path, monkeypatch):
    copy = tmp_path / "userscripts"
    shutil.copytree(DIR, copy)
    monkeypatch.setattr(userscripts, "USERSCRIPTS_DIR", copy)
    old = userscripts.bundle_info()["version"]
    (copy / "new.user.js").write_text("// ==UserScript==\n// @name         X\n// @version      1.0.0\n"
                                      "// @match        https://www.new.example/*\n// @grant        GM_getValue\n"
                                      "// ==/UserScript==\n// new site code\n", encoding="utf-8")
    text = client.get(URL).text
    assert "https://www.new.example/*" in header_lines(text, "match")
    assert "// new site code" in text
    new = userscripts.bundle_info()["version"]
    assert header_lines(text, "version") == [new]
    assert [int(p) for p in new.split(".")] > [int(p) for p in old.split(".")]


@pytest.mark.parametrize("old,new", [("1.0.9", "1.1.0"), ("1.9.9", "2.0.0"), ("1.0.0", "1.0.1")])
def test_bundle_version_grows_with_a_site_version(old, new):
    a = userscripts.bundle_version(6, ["1.0.0", old])
    b = userscripts.bundle_version(6, ["1.0.0", new])
    assert [int(p) for p in b.split(".")] > [int(p) for p in a.split(".")]


def test_bundle_version_grows_with_core():
    # A higher CORE_VERSION wins, also when a site was removed (then the sum is lower).
    a = userscripts.bundle_version(6, ["9.9.9", "1.0.0"])
    b = userscripts.bundle_version(7, ["1.0.0"])
    assert [int(p) for p in b.split(".")] > [int(p) for p in a.split(".")]


def test_tokens_page_list_has_no_bundle_file():
    assert userscripts.BUNDLE not in {s["file"] for s in userscripts.userscript_list()}
    assert not (DIR / userscripts.BUNDLE).exists()


@pytest.mark.parametrize("pattern,url,ok", [
    ("https://*.flixbus.nl/*", "https://shop.flixbus.nl/search?x=1", True),
    ("https://*.flixbus.nl/*", "https://flixbus.nl/", True),
    ("https://*.flixbus.nl/*", "https://evil.example/?.flixbus.nl/", False),
    ("https://www.bahn.de/*", "https://www.bahn.de/buchung", True),
    ("https://www.bahn.de/*", "https://www.bahn.de.evil.example/", False),
    ("https://www.bahn.de/*", "http://www.bahn.de/", False),
])
def test_match_regex(pattern, url, ok):
    assert bool(re.search(userscripts.match_regex(pattern), url)) is ok


STUBS = """
window.__gm = {server: 'https://ta.example', token: 'tok', trip: 5};
window.__ingest = [];
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = () => {};
window.GM_xmlhttpRequest = (d) => {
  if (d.url.startsWith('https://ta.example/api/trips')) {
    setTimeout(() => d.onload({status: 200, responseText: JSON.stringify([{id: 5, title: 'T'}])}), 0);
    return;
  }
  window.__ingest.push({url: d.url, body: JSON.parse(d.data)});
  setTimeout(() => d.onload({status: 200}), 0);
};
"""
BAHN = json.loads((ROOT / "tests" / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen.json").read_text("utf-8"))


@pytest.fixture
def browser_page(client):
    playwright = pytest.importorskip("playwright.sync_api")
    script = client.get(URL).text
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()

        def serve(route):
            if route.request.url.endswith("/web/api/angebote/fahrplan"):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(BAHN["response"]))
            else:
                route.fulfill(status=200, content_type="text/html", body="<html><body>test page</body></html>")

        pg.route("**/*", serve)
        pg.add_init_script(STUBS + script)
        yield pg
        browser.close()


def search(pg):
    pg.evaluate("b => fetch('/web/api/angebote/fahrplan', {method: 'POST', body: b}).then(r => r.json())",
                json.dumps(BAHN["request"]))


@pytest.mark.slow
def test_bundle_captures_on_a_site_page(browser_page):
    browser_page.goto("https://int.bahn.de/en/buchung/fahrplan/suche")
    search(browser_page)
    browser_page.wait_for_function("window.__ingest.length === 1")
    body = browser_page.evaluate("window.__ingest")[0]["body"]
    assert (body["source"], body["trip_id"]) == ("bahn.de", 5)
    assert body["raw"]["response"] == BAHN["response"]


@pytest.mark.slow
def test_site_part_runs_only_on_its_own_pages(browser_page):
    # The bahn.de part does not run on an NS page, so a response with a bahn.de path is not sent from there.
    browser_page.goto("https://www.nsinternational.com/en/")
    search(browser_page)
    browser_page.wait_for_timeout(300)
    assert browser_page.evaluate("window.__ingest") == []
    assert browser_page.evaluate("document.getElementById('ta-core-panel') !== null")
