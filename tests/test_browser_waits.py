"""`page.wait_for_function` must get no Promise (#986): it returns at once, also for a Promise of false, so a wait
such as `wait_for_function("caches.keys().then(...)")` does not wait. Use `tests.browser_wait.wait_js` for those."""

import ast
import os
from pathlib import Path

import pytest

from tests.browser_wait import wait_js

TESTS = Path(__file__).parent
ASYNC = (".then(", "async ", "await ", "Promise", "serviceWorker.ready", "caches.")


def _promise_waits(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    found = []
    for node in ast.walk(ast.parse(text)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "wait_for_function" and node.args):
            arg = ast.get_source_segment(text, node.args[0]) or ""
            if any(token in arg for token in ASYNC):
                found.append(f"{path.name}:{node.lineno}: {arg}")
    return found


def test_no_wait_for_function_gets_a_promise():
    found = [line for path in sorted(TESTS.rglob("*.py")) for line in _promise_waits(path)]
    assert found == [], "use tests.browser_wait.wait_js, wait_for_function does not wait for a Promise:\n" + \
        "\n".join(found)


def test_the_scan_finds_the_form_of_the_offline_test(tmp_path):
    bad = tmp_path / "test_x.py"
    bad.write_text('page.wait_for_function(f"{CACHED}.then(p => p.includes(\'/upcoming\'))")\n'
                   'page.wait_for_function("document.title === \'x\'")\n', encoding="utf-8")
    assert [line.split(":")[1] for line in _promise_waits(bad)] == ["1"]


@pytest.fixture
def page():
    from playwright.sync_api import sync_playwright

    exe = "/opt/pw-browsers/chromium"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        yield browser.new_page()
        browser.close()


@pytest.mark.slow
def test_wait_for_function_does_not_wait_for_a_promise_but_wait_js_does(page):
    page.evaluate("setTimeout(() => { window.done = true; }, 500)")
    late = "new Promise(r => setTimeout(() => r(window.done === true), 10))"
    page.wait_for_function(late, timeout=2000)  # the cause of #986: it returns although the value is false
    assert page.evaluate("window.done === true") is False
    assert wait_js(page, late, timeout=5) is True
    with pytest.raises(AssertionError, match="not true after"):
        wait_js(page, "new Promise(() => {})", timeout=1.5)  # never settles (as serviceWorker.ready with no worker)
