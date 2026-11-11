"""The panel links to the trip page on the server ("Open the trip", #2366). Playwright stubs GM_xmlhttpRequest, so no
request goes to a server or a travel site (P1)."""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = %s;
window.GM_getValue = (k, d) => (k in window.__gm ? window.__gm[k] : d);
window.GM_setValue = (k, v) => { window.__gm[k] = v; };
window.GM_info = () => ({ script: {} });
window.__body = '{}';
window.GM_xmlhttpRequest = (o) => {
  setTimeout(() => o.onload({ status: 200, responseText: window.__body }), 0);
};
"""
PAGE = "<html><head></head><body></body></html>"


@pytest.fixture
def open_page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()

        def load(gm):
            pg = browser.new_page()
            pg.set_content(PAGE)
            pg.add_script_tag(content=STUBS % json.dumps(gm))
            pg.add_script_tag(content=CORE.read_text(encoding="utf-8"))
            return pg

        yield load
        browser.close()


def link(pg):
    return pg.evaluate("""() => { const a = document.getElementById('ta-core-panel').shadowRoot
        .querySelector('.open-trip');
        return {hidden: a.hidden, href: a.getAttribute('href'), target: a.getAttribute('target'),
                rel: a.getAttribute('rel')}; }""")


def choose(pg, trip_id):
    pg.evaluate("""(id) => { const s = document.getElementById('ta-core-panel').shadowRoot.querySelector('.trip');
        if (!Array.from(s.options).some((o) => o.value === String(id))) {
          const o = document.createElement('option'); o.value = String(id); o.textContent = 'Trip ' + id;
          s.appendChild(o);
        }
        s.value = String(id);
        s.dispatchEvent(new Event('change')); }""", trip_id)


def test_a_selected_trip_shows_the_link_to_its_page(open_page):
    pg = open_page({"server": "https://travel.example", "trip": 12})
    assert link(pg) == {"hidden": False, "href": "https://travel.example/trips/12",
                        "target": "_blank", "rel": "noopener"}


def test_a_change_of_the_trip_changes_the_link(open_page):
    pg = open_page({"server": "https://travel.example", "trip": 12})
    choose(pg, 13)
    assert link(pg)["href"] == "https://travel.example/trips/13"
    assert link(pg)["hidden"] is False


def test_no_selected_trip_hides_the_link(open_page):
    pg = open_page({"server": "https://travel.example", "trip": 0})
    assert link(pg) == {"hidden": True, "href": None, "target": "_blank", "rel": "noopener"}


def test_no_server_url_hides_the_link(open_page):
    pg = open_page({"server": "", "trip": 12})
    assert link(pg)["hidden"] is True
    assert link(pg)["href"] is None


def test_the_trip_the_server_chose_gives_the_link(open_page):
    pg = open_page({"server": "https://travel.example", "trip": 12})
    pg.evaluate("window.__body = '{\"accepted\": 1, \"trip_id\": 13, \"trip_title\": \"Rome\"}'")
    pg.evaluate("TACore.send({ source: 'test', offers: [{ price: '1.00' }] })")
    pg.wait_for_function("() => document.getElementById('ta-core-panel').shadowRoot"
                         ".querySelector('.panel').textContent.includes('Rome')")
    assert link(pg)["href"] == "https://travel.example/trips/13"
