---
name: verify
description: Verify a change to travel-aggregator before commit. Selects the check level from the type of change. Use before each commit and when a ticket says "verify".
---

# Verify a change

Select the levels from the type of change. Each level also needs the levels before it.

| Change | Levels |
|---|---|
| Docs, tickets, data | 1 |
| Python code, parsers, migrations | 1, 3 |
| Pages, templates, static files, userscripts | 1, 2, 3, 4 |
| `Dockerfile`, `docker-compose.yml` | 1 and a `docker build` job of CI (`capture:skeleton` adds it) |

## Level 1: lint and fast tests (each change)

    ruff check .
    python3 -m pytest tests/test_<topic>.py ...

Both must pass before the commit. Do not change `README.md` in a ticket PR: the README PR at the end of the epic
does it (`python3 -m pytest -m readme` checks the routes and the settings then). Run only the tests of the change: the quick CI runs all fast tests.
A parser change: run its fixture tests (`tests/fixtures/<source>/`). A model change: an Alembic migration with it
(`alembic upgrade head` on an empty database, then `alembic check`).

## Level 2: slow tests (pages and userscripts)

    python3 -m pytest -m slow tests/test_<topic>_browser.py ...

Run only the slow test files of the change: the browser tests of the changed pages or userscripts and the new test
files, and also `tests/test_pages_width_browser.py` for a change of `app.css` or `base.html` (they act on each page).
The CI job `browser` runs all slow tests on each PR, and Automerge waits for it (#822: the full suite before each push
took 108 minutes per 100 PRs).

Playwright tests: the pages in a real browser, and each userscript on a local test page that replays a fixture
(never the real travel site, P1). A test launches Chromium with
`p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()`, `exe = "/opt/pw-browsers/chromium"`:
the cloud has only that browser, and the CI job `browser` has no such path (#738, `tests/test_playwright_launch.py`).

## Level 3: a run of the app

Start the app against the test database (`uvicorn app.main:app`), POST a fixture to `/api/ingest` with a test token,
and read the trip page with `curl`. Check the counts of the response and the ranked rows.

## Level 4: screenshots for the PR

For each changed page: a Playwright screenshot at 1280 px and at 390 px width (`device_scale_factor=2`), with test
data. Read each image (Read tool) and check the layout: no horizontal scroll at 390 px, no overlap, no raw HTML
from captured data. The CI job `screenshots` (the first page ticket adds it) uploads the same images as an artifact. Describe each image in the PR
body and link the run: the REST API cannot upload images.

## Level 5: the deployed preview (at the end of an epic)

    scripts/preview_check.sh            # waits up to 15 minutes until the preview runs origin/main

It checks `/api/health` (the commit) and the API with a test trip and offer, through the network secret of the
environment. "HTTP 401" means the environment has no network secret: say so in the epic and stop. Never ask for a
password or a token, and never test the pages there (the login is the owner's): levels 2 and 4 test
them locally.
