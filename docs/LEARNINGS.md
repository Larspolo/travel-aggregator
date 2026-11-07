# Learnings

The agent writes here what it learned the hard way. Each line must save time in a later session.

## Environment and libraries

## Code
- A test file name must not repeat a name in `framework/tests/` (rootdir import mode): pytest stops with "import file mismatch". Check `ls framework/tests` first.
- `addopts` of `pyproject.toml` has `-q`: do not add `-q` to pytest (`-qq` hides the "N passed" line). A Playwright script outside the tests: `chromium.launch(executable_path="/opt/pw-browsers/chromium")`.
- A Playwright touch `tap()` returns before the click of the gesture: wait for its result (`wait_for_function`), never read it once (#508).
