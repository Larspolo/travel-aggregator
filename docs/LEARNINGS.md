# Learnings

The agent writes here what it learned the hard way. Each line must save time in a later session.

## Environment and libraries

- Verify level 3 by hand (`alembic`, `uvicorn` on an own `initdb` cluster): the data directory must be in `mktemp -d /tmp/...` (user `postgres` cannot open the scratchpad), set `PYTHONPATH=$PWD`, and add `?client_encoding=utf8` to `DATABASE_URL` (else psycopg gets bytes from the SQL_ASCII cluster: "cannot use a string pattern on a bytes-like object").
- Level 3 with the trip page: a token and a trip with `tokens.create(make_sessionmaker(make_engine())(), "v3")` (`app.db`, no `SessionLocal`); set `SECRET_KEY` and `export OWNER_PASSWORD_HASH="$(python3 app/auth.py PW)"` in a second `export` after `PYTHONPATH` (one `export` runs the `$(...)` before `PYTHONPATH` is set); log in with `curl -c jar` GET `/login`, then POST `csrf_token` and `password` (#1404).

## Code
- A new `Weights` field needs a `Form` in `save_profile()` and an entry in `CHANGED` of `tests/test_profiles_store.py` (#1567).
- A test file name must not repeat a name in `framework/tests/` (rootdir import mode): pytest stops with "import file mismatch". Check `ls framework/tests` first.
- `addopts` of `pyproject.toml` has `-q`: do not add `-q` to pytest (`-qq` hides the "N passed" line). A Playwright script outside the tests: `chromium.launch(executable_path="/opt/pw-browsers/chromium")`.
- A Playwright touch `tap()` returns before the click of the gesture: wait for its result (`wait_for_function`), never read it once (#508).
- A trip-page layout: at 1280 px the results column is only about 935 px (the weights panel takes 18 rem). Measure the cell widths with Playwright before the screenshots (#627: 7 columns gave the route cell 97 px).
- A `clip-path` on an element also clips its absolutely positioned children and their taps: put a full-width bar trick (`box-shadow` + `clip-path`) on a `::before` layer, and test a dropdown with `elementFromPoint`, not only with its box (#688).
- Playwright `wait_for_function` returns at once when its expression gives a Promise, also a Promise of false (`caches.keys().then(...)`, `serviceWorker.ready.then(...)`): use `tests.browser_wait.wait_js` (#986: the offline test reloaded before the worker saved the page, 1 failure in 6). `tests/test_browser_waits.py` stops the wrong form.
- FastAPI reads an empty form value (`Form`) as not sent and uses the default: a blank field is not an error with `Form(None)` or `Form("0")`. For a field that must reject a blank, test the blank case; use a sentinel default if the field is optional (#1117).
- A migration test must downgrade to a named revision (`command.downgrade(cfg, "0020")`), never `"-1"` from head: the next migration breaks it (#1118).
- A change of a userscript needs a new `@version` and its sha256 under that version in `tests/data/userscript_versions.json`; else `tests/test_userscripts_lock.py` fails (#1199).
