"""The userscript panel has the design of the app (#1067): the app colors in light and dark mode, and a status line
that hides the controls and remembers it. Playwright stubs GM_*, so no request goes to a server or a site (P1)."""

import os
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parent.parent / "userscripts" / "core.js"
STUBS = """
window.__gm = {server: "https://ta.example", token: "t"};
window.GM_getValue = (k, d) => (k in window.__gm ? window.__gm[k] : d);
window.GM_setValue = (k, v) => { window.__gm[k] = v; };
window.GM_xmlhttpRequest = (d) => setTimeout(() => d.onload({status: 200, responseText: "[]"}), 0);
"""
ROOT = "document.getElementById('ta-core-panel').shadowRoot"


def test_core_style_has_the_app_tokens():
    text = CORE.read_text()
    for token in ("#5145d6", "#8f87ff", "#187a35", "#c4302b", "prefers-color-scheme: dark", "--radius: 8px"):
        assert token in text


def _open(p, scheme, gm_extra=""):
    exe = "/opt/pw-browsers/chromium"
    browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
    page = browser.new_page(color_scheme=scheme)
    page.set_content("<html><body style='background:#fff'></body></html>")
    page.add_script_tag(content=STUBS + gm_extra)
    page.add_script_tag(content=CORE.read_text())
    return browser, page


def _style(page, sel, prop):
    return page.evaluate(f"getComputedStyle({ROOT}.querySelector('{sel}')).{prop}")


@pytest.mark.slow
@pytest.mark.parametrize("scheme,surface,accent", [("light", "rgb(255, 255, 255)", "rgb(81, 69, 214)"),
                                                   ("dark", "rgb(21, 21, 26)", "rgb(143, 135, 255)")])
def test_panel_uses_app_colors(scheme, surface, accent):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page = _open(p, scheme)
        assert _style(page, ".panel", "backgroundColor") == surface
        assert _style(page, ".controls", "borderRadius") == "8px"
        assert _style(page, ".send", "backgroundColor") == accent
        page.evaluate("TACore.sent(3)")
        assert _style(page, ".panel", "borderLeftColor") != _style(page, ".panel", "borderTopColor")
        browser.close()


@pytest.mark.slow
def test_status_click_collapses_and_remembers():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser, page = _open(p, "light")
        assert _style(page, ".controls", "display") == "flex"
        page.evaluate(f"{ROOT}.querySelector('.panel').click()")
        assert _style(page, ".controls", "display") == "none"
        assert page.evaluate("window.__gm.collapsed") is True
        browser.close()
        browser, page = _open(p, "light", "window.__gm.collapsed = true;")
        assert _style(page, ".controls", "display") == "none"
        assert _style(page, ".panel", "display") != "none"
        page.evaluate(f"{ROOT}.querySelector('.set-server').click()")
        assert _style(page, ".ask", "display") == "flex"
        assert page.evaluate("window.__gm.collapsed") is False
        browser.close()
