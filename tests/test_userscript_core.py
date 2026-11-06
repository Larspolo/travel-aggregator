"""The userscript core shows a floating status panel inside a Shadow DOM (#30)."""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow
CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = {};
window.GM_getValue = (k, d) => (k in window.__gm ? window.__gm[k] : d);
window.GM_setValue = (k, v) => { window.__gm[k] = v; };
window.GM_xmlhttpRequest = () => {};
"""
PAGE = "<html><head><style>div { color: red !important; display: none !important; }</style></head><body></body></html>"


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        pg.set_content(PAGE)
        pg.add_script_tag(content=STUBS)
        pg.add_script_tag(content=CORE.read_text())
        yield pg
        browser.close()


def panel(pg):
    return pg.evaluate("""() => { const h = document.getElementById('ta-core-panel');
        const b = h.shadowRoot.querySelector('.panel'); const s = getComputedStyle(b);
        return {shadow: !!h.shadowRoot, text: b.textContent, color: s.color, bg: s.backgroundColor,
                position: s.position, display: s.display}; }""")


def test_panel_shows_in_shadow_dom(page):
    p = panel(page)
    assert p["shadow"] and p["position"] == "fixed" and p["display"] != "none"
    assert p["text"]


def test_sent_shows_count(page):
    page.evaluate("TACore.sent(14)")
    assert panel(page)["text"] == "Captured 14 offers → sent ✓"
    page.evaluate("TACore.report(3)")
    assert panel(page)["text"] == "Captured 3 offers"


def test_error_has_other_style(page):
    page.evaluate("TACore.sent(1)")
    ok = panel(page)
    page.evaluate("TACore.panel.setStatus('No token', 'error')")
    err = panel(page)
    assert err["text"] == "No token"
    assert (err["color"], err["bg"]) != (ok["color"], ok["bg"])


def test_gm_wrapper_uses_stubs(page):
    page.evaluate("TACore.gm.setValue('token', 'abc')")
    assert page.evaluate("TACore.gm.getValue('token', null)") == "abc"
