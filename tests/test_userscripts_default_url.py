"""The userscript core uses the server that installed it as the default server URL (#392): the origin of the
@downloadURL, when it is https and not GitHub. A server URL that the owner sets keeps priority."""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
PAGE = "<html><body></body></html>"


def load(p, download_url, stored=None):
    stubs = f"""
    window.__gm = {{}};
    {'window.__gm.server = ' + repr(stored) + ';' if stored is not None else ''}
    window.GM_getValue = (k, d) => (k in window.__gm ? window.__gm[k] : d);
    window.GM_setValue = (k, v) => {{ window.__gm[k] = v; }};
    window.GM_xmlhttpRequest = () => {{}};
    window.GM_info = {{ script: {{ downloadURL: {download_url!r} }} }};
    """
    p.add_script_tag(content=stubs)
    p.add_script_tag(content=CORE.read_text(encoding="utf-8"))
    return p.evaluate("() => TACore.server()")


@pytest.fixture
def browser_page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        pg.set_content(PAGE)
        yield pg
        browser.close()


def test_download_url_gives_the_default_server(browser_page):
    url = "https://travel.example/userscripts/bahn.user.js"
    assert load(browser_page, url) == "https://travel.example"


def test_a_set_server_wins(browser_page):
    url = "https://travel.example/userscripts/bahn.user.js"
    assert load(browser_page, url, stored="https://mine.example/") == "https://mine.example"


def test_github_download_url_gives_no_default(browser_page):
    url = "https://raw.githubusercontent.com/Larspolo/travel-aggregator/main/userscripts/bahn.user.js"
    assert load(browser_page, url) == ""


def test_http_download_url_gives_no_default(browser_page):
    assert load(browser_page, "http://travel.example/userscripts/bahn.user.js") == ""


def test_no_download_url_gives_no_default(browser_page):
    assert load(browser_page, "") == ""
