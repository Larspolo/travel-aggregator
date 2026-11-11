"""Wait for the value of a JavaScript expression in a Playwright page (#986).

`page.wait_for_function` returns at once when its expression gives a Promise, also a Promise of false: it does not
wait for the value. So `wait_for_function("caches.keys().then(...)")` did not wait, and the offline test of #963
reloaded the page before the service worker saved it (about 1 failure in 6 runs). `page.evaluate` waits for a
Promise, so `wait_js` asks it again until the value is true. `tests/test_browser_waits.py` stops the wrong form.
"""

import time


def wait_js(page, expression: str, timeout: float = 10.0, interval: float = 0.05):
    """Evaluate `expression` (it can give a Promise) until its value is truthy, and return that value.
    AssertionError after `timeout` seconds. Each try waits at most 1 s for the Promise (for example
    `navigator.serviceWorker.ready` with no worker never settles), so the call cannot hang."""
    end = time.monotonic() + timeout
    probe = f"Promise.race([Promise.resolve().then(() => ({expression})), new Promise(r => setTimeout(r, 1000))])"
    while True:
        value = page.evaluate(probe)
        if value:
            return value
        if time.monotonic() >= end:
            raise AssertionError(f"{expression!r} is not true after {timeout} s (last value: {value!r})")
        page.wait_for_timeout(interval * 1000)
