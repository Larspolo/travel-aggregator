"""No offers seen (#1756): a results page of bahn.de with no accepted response shows the panel line and sends one
POST /api/silent (#1755). A response, or a page that is not a results page, gives no line and no POST."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
USERSCRIPTS = Path(__file__).resolve().parent.parent / "userscripts"
CORE_SRC = (USERSCRIPTS / "core.js").read_text(encoding="utf-8")
BAHN_SRC = (USERSCRIPTS / "bahn.user.js").read_text(encoding="utf-8")
SHORT_MS = 2000  # the test value of SILENT_MS (the constant of core.js, shortened for the test)
RESULTS = "https://www.bahn.de/buchung/fahrplan/suche?so=A"
LINE = "No offers seen on this page"
STUBS = """
window.__gm = {server: 'https://ta.example', token: 'tok'};
window.__sent = [];
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = () => {};
window.GM_xmlhttpRequest = (d) => { window.__sent.push({url: d.url, body: JSON.parse(d.data)}); };
"""
EARLY_FETCH = """
fetch('/web/api/angebote/fahrplan', {method: 'POST', body: '{}'}).then((r) => r.text()).then(() => {
  window.__got = true;
});
"""


@pytest.fixture
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        yield b
        b.close()


def open_page(browser, url, answer=None, early_fetch=False):
    core = CORE_SRC.replace("const SILENT_MS = 30000;", f"const SILENT_MS = {SHORT_MS};")
    assert core != CORE_SRC, "the constant SILENT_MS is not in core.js"
    page = browser.new_context().new_page()

    def route(r):
        if "/web/api/angebote/" in r.request.url:
            if answer is None:
                r.fulfill(status=404, body="")
            else:
                r.fulfill(status=200, content_type="application/json", body=json.dumps(answer))
        else:
            r.fulfill(status=200, content_type="text/html", body="<html><body></body></html>")

    page.route("https://www.bahn.de/**", route)
    page.add_init_script(STUBS)
    page.add_init_script(core)
    page.add_init_script(BAHN_SRC)
    if early_fetch:
        page.add_init_script(EARLY_FETCH)
    page.goto(url)
    return page


def panel_text(page):
    return page.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').textContent")


def silent_posts(page):
    return [s for s in page.evaluate("window.__sent") if s["url"].endswith("/api/silent")]


def test_no_response_shows_the_line_and_posts_once(browser):
    page = open_page(browser, RESULTS)
    page.wait_for_function(f"document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           f".textContent.includes('{LINE}')", timeout=SHORT_MS * 5)
    page.wait_for_function("window.__sent.some((s) => s.url.endsWith('/api/silent'))", timeout=SHORT_MS * 5)
    posts = silent_posts(page)
    assert len(posts) == 1
    assert posts[0]["url"] == "https://ta.example/api/silent"
    assert posts[0]["body"]["source"] == "bahn.de"
    assert posts[0]["body"]["page_url"] == "/buchung/fahrplan/suche?so=A"
    assert posts[0]["body"]["script_version"] == "1.2.0"
    page.wait_for_timeout(SHORT_MS)
    assert len(silent_posts(page)) == 1


def test_accepted_response_before_the_end_gives_no_line_and_no_post(browser):
    answer = {"verbindungen": [{"reiseAngebote": [{"name": "Sparpreis", "klasse": "2", "preis": {"betrag": 10}}]}]}
    page = open_page(browser, RESULTS, answer=answer, early_fetch=True)
    page.wait_for_function("window.__got === true", timeout=SHORT_MS)
    page.wait_for_timeout(SHORT_MS + 500)
    assert LINE not in panel_text(page)
    assert silent_posts(page) == []


def test_page_that_is_not_a_results_page_gives_no_line(browser):
    page = open_page(browser, "https://www.bahn.de/")
    page.wait_for_timeout(SHORT_MS + 500)
    assert LINE not in panel_text(page)
    assert silent_posts(page) == []


def test_leaving_the_results_page_stops_the_timer(browser):
    page = open_page(browser, RESULTS)
    page.evaluate("history.pushState({}, '', '/')")
    page.wait_for_timeout(SHORT_MS + 500)
    assert LINE not in panel_text(page)
    assert silent_posts(page) == []
