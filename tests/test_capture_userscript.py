"""`capture.py userscript` prints a Tampermonkey script that installs the hook at document start, so it records a
search that is a full page load with fast results (Skyscanner, #463). Playwright serves all URLs from the test, so no
request goes to a travel site (P1)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import capture  # noqa: E402

SITE = "https://www.skyscanner.nl/*"


def test_userscript_runs_the_hook_at_document_start_on_one_site_with_no_grants():
    js = capture.userscript(r"skyscanner\.nl/g/(radar|michelin)", SITE)
    head = js.split("// ==/UserScript==")[0]
    assert head.startswith("// ==UserScript==")
    assert f"// @match        {SITE}\n" in head
    assert "// @run-at       document-start\n" in head
    assert "// @grant        none\n" in head
    assert head.count("@match") == 1
    assert capture.hook(r"skyscanner\.nl/g/(radar|michelin)") in js


@pytest.mark.parametrize("site", ["http://www.skyscanner.nl/*", "*://*/*", "https://a.nl/*\n// @match *://*/*", ""])
def test_userscript_refuses_a_site_that_is_not_one_https_pattern(site):
    with pytest.raises(SystemExit):
        capture.userscript(".", site)


def test_userscript_command_prints_the_script(capsys):
    assert capture.main(["userscript", "--match", "/g/radar/", "--site", SITE]) == 0
    assert "@run-at       document-start" in capsys.readouterr().out


@pytest.mark.slow
def test_userscript_records_a_response_of_the_first_page_load():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()
        page_html = ("<html><body><script>fetch(new Request('/g/radar/api/v2/web-unified-search/', "
                     "{method: 'POST', body: '{}'})).then(r => r.json()).then(d => { window.done = d; });"
                     "</script></body></html>")

        def serve(route):
            if "/g/radar/" in route.request.url:
                route.fulfill(status=200, content_type="application/json", body='{"itineraries": {"results": [1]}}')
            else:
                route.fulfill(status=200, content_type="text/html", body=page_html)

        pg.route("**/*", serve)
        # Tampermonkey runs a document-start script before the scripts of the page, as an init script does.
        pg.add_init_script(capture.userscript("/g/radar/", SITE))
        pg.goto("https://www.skyscanner.nl/transport/vluchten/ams/lis/261201/")
        pg.wait_for_function("window.done && window.__taCap.entries.length === 1")
        e = pg.evaluate("window.__taCap.entries[0]")
        browser.close()
    assert e["request"]["method"] == "POST"
    assert e["request"]["postData"]["text"] == "{}"
    assert json.loads(e["response"]["content"]["text"]) == {"itineraries": {"results": [1]}}
