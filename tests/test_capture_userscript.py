"""`scripts/capture-hook.user.js` is the capture script of Tampermonkey (#463): installed once, updated from `main`, and
off until `capture.py hook` turns it on in a tab. Then it records a search that is a full page load with fast results
(Skyscanner) from the first request. Playwright serves all URLs from the test, so no request goes to a travel site
(P1)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import capture  # noqa: E402


def header(js):
    return js.split("// ==/UserScript==")[0]


def test_the_committed_script_is_up_to_date():
    assert capture.USERSCRIPT_FILE.read_text("utf-8") == capture.userscript(), \
        "run: python3 tools/capture.py userscript"


def test_a_changed_script_has_a_new_version_else_tampermonkey_does_not_update_it():
    assert capture.userscript_hash() == capture.USERSCRIPT_HASH, (
        "the capture script changed: add 1 to USERSCRIPT_VERSION in tools/capture.py, set USERSCRIPT_HASH = "
        f"{capture.userscript_hash()!r}, and run: python3 tools/capture.py userscript")


def test_the_script_updates_from_main_and_runs_at_document_start_with_no_grants():
    head = header(capture.userscript())
    assert f"// @version      {capture.USERSCRIPT_VERSION}\n" in head
    url = capture.userscript_url()
    assert f"// @updateURL    {url}\n" in head
    assert f"// @downloadURL  {url}\n" in head
    cfg = capture.config()
    assert url == f"https://raw.githubusercontent.com/{cfg['repo']}/{cfg.get('branch', 'main')}/scripts/capture-hook.user.js"
    assert "// @run-at       document-start\n" in head
    assert "// @grant        none\n" in head
    assert head.count("@grant") == 1


def test_the_script_runs_on_the_sites_of_the_userscripts_and_the_extra_sites_only():
    head = header(capture.userscript())
    sites = capture.capture_sites()
    assert {"https://www.bahn.de/*", "https://www.nsinternational.com/*", "https://www.skyscanner.nl/*"} <= set(sites)
    assert [line.split()[-1] for line in head.splitlines() if "@match" in line] == sites
    assert all(s.startswith("https://") and "*://" not in s and s != "https://*/*" for s in sites)


def test_userscript_check_fails_when_the_file_is_old(tmp_path, monkeypatch, capsys):
    old = tmp_path / "capture-hook.user.js"
    old.write_text("// old\n", "utf-8")
    monkeypatch.setattr(capture, "USERSCRIPT_FILE", old)
    monkeypatch.setattr(capture, "ROOT", tmp_path)
    assert capture.main(["userscript", "--check"]) == 1
    assert old.read_text("utf-8") == "// old\n"
    assert capture.main(["userscript"]) == 0
    assert old.read_text("utf-8") == capture.userscript()
    assert capture.main(["userscript", "--check"]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["up_to_date"] is True


PAGE = ("<html><body><script>fetch(new Request('/g/radar/api/v2/web-unified-search/', "
        "{method: 'POST', body: '{}'})).then(r => r.json()).then(d => { window.done = d; });"
        "</script></body></html>")
URL = "https://www.skyscanner.nl/transport/vluchten/ams/lis/261201/"


@pytest.fixture
def page():
    playwright = pytest.importorskip("playwright.sync_api")
    exe = "/opt/pw-browsers/chromium"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = browser.new_page()

        def serve(route):
            if "/g/radar/" in route.request.url:
                route.fulfill(status=200, content_type="application/json", body='{"itineraries": {"results": [1]}}')
            else:
                route.fulfill(status=200, content_type="text/html", body=PAGE)

        pg.route("**/*", serve)
        # Tampermonkey runs a document-start script before the scripts of the page, as an init script does.
        pg.add_init_script(capture.userscript())
        yield pg
        browser.close()


@pytest.mark.slow
def test_the_script_does_nothing_in_a_tab_with_no_flag(page):
    page.goto(URL)
    page.wait_for_function("window.done")
    assert page.evaluate("[window.__taCapAuto, typeof window.__taCap]") == [capture.USERSCRIPT_VERSION, "undefined"]


@pytest.mark.slow
def test_the_hook_turns_the_script_on_for_the_next_page_loads_and_stop_turns_it_off(page):
    page.goto(URL)
    state = json.loads(page.evaluate(capture.hook(r"/g/radar/")))
    assert state["auto"] == capture.USERSCRIPT_VERSION
    page.goto(URL)          # a new search is a full page load: the script records from the first request
    page.wait_for_function("window.done && window.__taCap && window.__taCap.entries.length === 1")
    e = page.evaluate("window.__taCap.entries[0]")
    assert e["request"]["method"] == "POST"
    assert e["request"]["postData"]["text"] == "{}"
    assert json.loads(e["response"]["content"]["text"]) == {"itineraries": {"results": [1]}}
    assert json.loads(page.evaluate("window.__taCap.stop()")) == {"stopped": True}
    page.goto(URL)
    page.wait_for_function("window.done")
    assert page.evaluate("typeof window.__taCap") == "undefined"
