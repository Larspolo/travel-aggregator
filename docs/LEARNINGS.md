# Learnings

The agent writes here what it learned the hard way. Each line must save time in a later session.

## Environment and libraries

- Verify level 3 by hand (`alembic`, `uvicorn` on an own `initdb` cluster): the data directory must be in `mktemp -d /tmp/...` (user `postgres` cannot open the scratchpad), set `PYTHONPATH=$PWD`, and add `?client_encoding=utf8` to `DATABASE_URL` (else psycopg gets bytes from the SQL_ASCII cluster: "cannot use a string pattern on a bytes-like object").

## Code
- A test file name must not repeat a name in `framework/tests/` (rootdir import mode): pytest stops with "import file mismatch". Check `ls framework/tests` first.
- `addopts` of `pyproject.toml` has `-q`: do not add `-q` to pytest (`-qq` hides the "N passed" line). A Playwright script outside the tests: `chromium.launch(executable_path="/opt/pw-browsers/chromium")`.
- A Playwright touch `tap()` returns before the click of the gesture: wait for its result (`wait_for_function`), never read it once (#508).
- A trip-page layout: at 1280 px the results column is only about 935 px (the weights panel takes 18 rem). Measure the cell widths with Playwright before the screenshots (#627: 7 columns gave the route cell 97 px).
- A `clip-path` on an element also clips its absolutely positioned children and their taps: put a full-width bar trick (`box-shadow` + `clip-path`) on a `::before` layer, and test a dropdown with `elementFromPoint`, not only with its box (#688).
- Playwright `wait_for_function` returns at once when its expression gives a Promise, also a Promise of false (`caches.keys().then(...)`, `serviceWorker.ready.then(...)`): use `tests.browser_wait.wait_js` (#986: the offline test reloaded before the worker saved the page, 1 failure in 6). `tests/test_browser_waits.py` stops the wrong form.
