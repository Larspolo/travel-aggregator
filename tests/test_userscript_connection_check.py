"""The "Test the connection" check of the userscript panel (#2048): it shows whether the server and the token work."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
SERVER = "https://ta.example"
STUBS = """
window.__gm = {server: 'https://ta.example', token: 'tok'};
window.__menu = [];
window.__sent = [];
window.__answer = {};
window.GM_getValue = (k, d) => (k in window.__gm ? JSON.parse(JSON.stringify(window.__gm[k])) : d);
window.GM_setValue = (k, v) => { window.__gm[k] = JSON.parse(JSON.stringify(v)); };
window.GM_registerMenuCommand = (name) => { window.__menu.push(name); };
window.GM_xmlhttpRequest = (d) => {
  const path = new URL(d.url).pathname;
  window.__sent.push({url: d.url, auth: (d.headers || {}).Authorization});
  const a = window.__answer[path] || {status: 200, body: '[]'};
  setTimeout(() => {
    if (a.error) return d.onerror({});
    d.onload({status: a.status, responseText: a.body, responseHeaders: a.headers || ''});
  }, 0);
};
"""
HEALTH_OK = {"status": 200, "body": json.dumps({"status": "ok", "commit": "dev", "built": "dev"})}


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        pg.set_content("<html><body></body></html>")
        pg.add_script_tag(content=STUBS)
        pg.add_script_tag(content=CORE.read_text(encoding="utf-8"))
        yield pg
        browser.close()


def status(pg) -> str:
    return pg.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').textContent")


def answer(pg, path, status_code, body=None, headers=""):
    pg.evaluate("([p, a]) => { window.__answer[p] = a; }",
                [path, {"status": status_code, "body": json.dumps(body) if body is not None else "", "headers": headers}])


def press_test(pg, expected: str) -> None:
    pg.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.test-connection').click()")
    pg.wait_for_function("(t) => document.getElementById('ta-core-panel').shadowRoot"
                         ".querySelector('.panel').textContent === t", arg=expected)


def test_valid_token_without_end_date(page):
    answer(page, "/api/health", 200, {"status": "ok"})
    answer(page, "/api/token", 200, {"name": "laptop", "expires_at": None})
    press_test(page, "Server OK, token OK (laptop)")
    assert "ok" in page.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').className")


def test_valid_token_with_end_date(page):
    answer(page, "/api/health", 200, {"status": "ok"})
    answer(page, "/api/token", 200, {"name": "laptop", "expires_at": "2030-01-02T03:04:05+00:00"})
    press_test(page, "Server OK, token OK (laptop), ends 2030-01-02")


def test_revoked_token(page):
    answer(page, "/api/health", 200, {"status": "ok"})
    answer(page, "/api/token", 401, {"detail": "token revoked"})
    press_test(page, "Token revoked: make a new token on the Userscripts page")


def test_expired_token(page):
    answer(page, "/api/health", 200, {"status": "ok"})
    answer(page, "/api/token", 401, {"detail": "token expired"})
    press_test(page, "Token expired: make a new token on the Userscripts page")


def test_unknown_token(page):
    answer(page, "/api/health", 200, {"status": "ok"})
    answer(page, "/api/token", 401, {"detail": "invalid or missing API token"})
    press_test(page, "Wrong token: copy it again from the Userscripts page")


def test_too_many_bad_tokens(page):
    answer(page, "/api/health", 200, {"status": "ok"})
    answer(page, "/api/token", 429, {"detail": "too many bad API tokens"}, headers="Retry-After: 840\r\n")
    press_test(page, "Too many bad tokens: wait 840 s")


def test_no_answer_from_server(page):
    page.evaluate("window.__answer['/api/health'] = {error: true}")
    press_test(page, f"No answer from {SERVER}")


def test_not_a_travel_aggregator(page):
    answer(page, "/api/health", 200, {"status": "fail"})
    press_test(page, "No travel-aggregator at this URL")


def test_no_http_url_asks_for_server_first(page):
    page.evaluate("window.__gm.server = 'ftp://ta.example'; window.__sent = []")
    press_test(page, "Set the server URL first")
    assert not any("/api/" in s["url"] for s in page.evaluate("window.__sent"))


def test_set_api_token_checks_the_new_token(page):
    answer(page, "/api/health", 200, {"status": "ok"})
    answer(page, "/api/token", 200, {"name": "new", "expires_at": None})
    page.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.set-token').click()")
    page.evaluate("""() => {
        const root = document.getElementById('ta-core-panel').shadowRoot;
        root.querySelector('.ask-input').value = 'fresh-token';
        root.querySelector('.ask-save').click();
    }""")
    page.wait_for_function("(t) => document.getElementById('ta-core-panel').shadowRoot"
                           ".querySelector('.panel').textContent === t", arg="Server OK, token OK (new)")
    token_calls = [s for s in page.evaluate("window.__sent") if s["url"].endswith("/api/token")]
    assert token_calls and token_calls[-1]["auth"] == "Bearer fresh-token"


def test_requests_go_only_to_the_configured_server(page):
    answer(page, "/api/health", 200, {"status": "ok"})
    answer(page, "/api/token", 200, {"name": "laptop", "expires_at": None})
    press_test(page, "Server OK, token OK (laptop)")
    urls = [s["url"] for s in page.evaluate("window.__sent")]
    assert urls and all(u.startswith(SERVER + "/") for u in urls)
