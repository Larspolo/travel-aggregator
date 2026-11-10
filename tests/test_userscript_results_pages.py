"""The results page of each other userscript (#1757): no accepted response on it gives "No offers seen on this page";
the start page of the site gives no line. The URLs come from the fixtures and their READMEs (P1: no site request)."""

import pytest

from tests.test_userscript_silent import CORE_SRC, LINE, SHORT_MS, STUBS, USERSCRIPTS, browser  # noqa: F401

pytestmark = pytest.mark.slow
CASES = [  # script, results page (fixtures), start page
    ("eurostar.user.js", "https://www.eurostar.com/search/uk-en?adult=1&origin=1&destination=2&outbound=2026-12-01",
     "https://www.eurostar.com/uk-en"),
    ("sncf.user.js", "https://www.sncf-connect.com/app/home/shop/results/outward", "https://www.sncf-connect.com/"),
]


def _open(browser, script, url):  # noqa: F811
    core = CORE_SRC.replace("const SILENT_MS = 30000;", f"const SILENT_MS = {SHORT_MS};")
    page = browser.new_context().new_page()
    page.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html", body="<html><body></body></html>")
               if r.request.resource_type == "document" else r.fulfill(status=404, body=""))
    page.add_init_script(STUBS)
    page.add_init_script(core)
    page.add_init_script((USERSCRIPTS / script).read_text(encoding="utf-8"))
    page.goto(url)
    return page


def _text(page):
    return page.evaluate("document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel').textContent")


@pytest.mark.parametrize("script,results,start", CASES)
def test_the_results_page_shows_the_line(browser, script, results, start):  # noqa: F811
    page = _open(browser, script, results)
    page.wait_for_function(f"document.getElementById('ta-core-panel').shadowRoot.querySelector('.panel')"
                           f".textContent.includes('{LINE}')", timeout=SHORT_MS * 5)


@pytest.mark.parametrize("script,results,start", CASES)
def test_the_start_page_shows_no_line(browser, script, results, start):  # noqa: F811
    page = _open(browser, script, start)
    page.wait_for_timeout(SHORT_MS + 500)
    assert LINE not in _text(page)
