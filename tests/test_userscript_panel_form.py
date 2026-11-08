"""The userscript panel asks in its own form, not with a browser dialog (#1066, P6): Playwright and agent tools can use
it with no person. Playwright stubs GM_xmlhttpRequest, so no request goes to a server or a travel site (P1)."""

import os
import re
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = {server: "https://old.example/", token: "old"};
window.GM_getValue = (k, d) => (k in window.__gm ? window.__gm[k] : d);
window.GM_setValue = (k, v) => { window.__gm[k] = v; };
window.GM_xmlhttpRequest = (d) => setTimeout(() => d.onload({status: 200, responseText: "[]"}), 0);
"""
ROOT = "document.getElementById('ta-core-panel').shadowRoot"


def test_core_has_no_browser_dialog():
    assert not re.search(r"\b(prompt|confirm|alert)\s*\(", CORE.read_text())


@pytest.fixture
def pg():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        page = browser.new_page()
        page.on("dialog", lambda d: pytest.fail("a browser dialog opened"))
        page.route("https://ta.test/", lambda r: r.fulfill(body="<html><body></body></html>", content_type="text/html"))
        page.goto("https://ta.test/")
        page.add_script_tag(content=STUBS)
        page.add_script_tag(content=CORE.read_text())
        yield page
        browser.close()


def _q(sel):
    return f"{ROOT}.querySelector('{sel}')"


@pytest.mark.slow
def test_server_field_shows_value_and_cancel_changes_nothing(pg):
    assert pg.evaluate(f"{_q('.ask')}.hidden") is True
    pg.evaluate(f"{_q('.set-server')}.click()")
    assert pg.evaluate(f"{_q('.ask')}.hidden") is False
    assert pg.evaluate(f"{_q('.ask-input')}.value") == "https://old.example"
    pg.evaluate(f"{_q('.ask-input')}.value = 'https://x.example/'")
    pg.evaluate(f"{_q('.ask-cancel')}.click()")
    assert pg.evaluate(f"{_q('.ask')}.hidden") is True
    assert pg.evaluate("window.__gm.server") == "https://old.example/"


@pytest.mark.slow
def test_token_field_is_password_enter_saves_escape_cancels(pg):
    pg.evaluate(f"{_q('.set-token')}.click()")
    assert pg.evaluate(f"{_q('.ask-input')}.type") == "password"
    assert pg.evaluate(f"{_q('.ask-input')}.value") == ""
    pg.locator("#ta-core-panel .ask-input").press("Escape")
    assert pg.evaluate("window.__gm.token") == "old"
    pg.evaluate(f"{_q('.set-token')}.click()")
    pg.locator("#ta-core-panel .ask-input").fill(" new-token ")
    pg.locator("#ta-core-panel .ask-input").press("Enter")
    pg.wait_for_function("window.__gm.token === 'new-token'")
