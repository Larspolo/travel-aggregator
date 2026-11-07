"""The userscript panel has "Server URL" and "API token" buttons (#536): the owner did not find the Tampermonkey menu."""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = {};
window.GM_getValue = (k, d) => (k in window.__gm ? window.__gm[k] : d);
window.GM_setValue = (k, v) => { window.__gm[k] = v; };
window.GM_xmlhttpRequest = (d) => setTimeout(() => d.onload({status: 200, responseText: "[]"}), 0);
window.__answers = ["https://ta.example/", " secret-token "];
window.prompt = () => window.__answers.shift();
"""


def test_panel_buttons_set_server_and_token():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        pg.route("https://ta.test/", lambda r: r.fulfill(body="<html><body></body></html>", content_type="text/html"))
        pg.goto("https://ta.test/")
        pg.add_script_tag(content=STUBS)
        pg.add_script_tag(content=CORE.read_text())
        root = "document.getElementById('ta-core-panel').shadowRoot"
        pg.evaluate(f"{root}.querySelector('.set-server').click()")
        pg.evaluate(f"{root}.querySelector('.set-token').click()")
        assert pg.evaluate("window.__gm.server") == "https://ta.example/"
        assert pg.evaluate("window.__gm.token") == "secret-token"
        browser.close()
