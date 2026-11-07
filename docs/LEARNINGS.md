# Learnings

The agent writes here what it learned the hard way. Each line must save time in a later session.

## Environment and libraries

- Verify level 3 by hand (`alembic`, `uvicorn` on an own `initdb` cluster): the data directory must be in `mktemp -d /tmp/...` (user `postgres` cannot open the scratchpad), set `PYTHONPATH=$PWD`, and add `?client_encoding=utf8` to `DATABASE_URL` (else psycopg gets bytes from the SQL_ASCII cluster: "cannot use a string pattern on a bytes-like object").

## Code
- A test file name must not repeat a name in `framework/tests/` (rootdir import mode): pytest stops with "import file mismatch". Check `ls framework/tests` first.
- `addopts` of `pyproject.toml` has `-q`: do not add `-q` to pytest (`-qq` hides the "N passed" line). A Playwright script outside the tests: `chromium.launch(executable_path="/opt/pw-browsers/chromium")`.
- A Playwright touch `tap()` returns before the click of the gesture: wait for its result (`wait_for_function`), never read it once (#508).
- A new module-level limiter or cache in `app/` is global test state (all TestClient requests come from `testclient`): reset it in the autouse fixture `_reset_limiters` of `tests/conftest.py`, else the split of the xdist workers makes main red later (#521).
