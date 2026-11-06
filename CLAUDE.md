# travel-aggregator – guide for Claude Code

travel-aggregator is a self-hosted web app that collects the train, bus and flight offers that the owner sees on
travel sites (through Tampermonkey userscripts and an ingest API) and ranks them by a personal "effective cost".
The owner compares all options of a trip on one page; the full specification is `docs/SPEC.md`.

The owner is **Larspolo**. The agent system: `framework/docs/SYSTEM.md`.
The project values: `agent.toml`. Write all text in ASD-STE100 Simplified Technical English.

## Commands

| Task | Command |
|---|---|
| Install | `python3 -m pip install -r requirements-dev.txt` |
| Lint | `ruff check .` |
| Tests of a change | `python3 -m pytest tests/test_a.py ...` (`-n auto` for many files) |
| Fast tests (CI) | `python3 -m pytest -n auto` |
| Slow tests | `python3 -m pytest -m slow` (Playwright browser tests of the pages and the userscripts) |
| Development server | `docker compose up --build` (owner's computer; the cloud has no Docker daemon) |
| App without Docker | `uvicorn app.main:app --reload` with `DATABASE_URL` set |

The tests need PostgreSQL 16: `TEST_DATABASE_URL`, else `tests/conftest.py` starts a temporary cluster with
`initdb` and `pg_ctl` from `/usr/lib/postgresql/16/bin` (CI has a `postgres:16` service). In a cloud session,
Playwright uses the browser at `/opt/pw-browsers/chromium`: do not run `playwright install` there.

## Code map (planned)

- `app/` – the FastAPI app: `main.py` (app and routers), `api/` (ingest, trips, health), `web/` (pages, Jinja2
  `templates/`, `static/` with htmx), `models.py` (SQLAlchemy 2.x), `schemas.py` (Pydantic ingest models),
  `ingest.py` (fingerprint, upsert, price history), `ranking.py` (effective cost and breakdown), `auth.py`.
- `app/parsers/` – one parser class per source with one interface (`source`, `version`, `parse(raw) -> offers`).
- `migrations/` – Alembic. They run at the start of the container.
- `userscripts/` – `core.js` (panel, queue, config, `GM_xmlhttpRequest`) and one `<source>.user.js` per site.
- `tests/` – pytest; `tests/fixtures/<source>/` holds trimmed raw payloads.
- `deploy/` – Caddy and nginx examples. `Dockerfile`, `docker-compose.yml`, `.env.example`, `Makefile` at the root.

A new source is one userscript and one server parser, with its fixtures, and nothing else.

## Rules of the domain

- **Passive capture only** (P1): no code sends a request to a travel site, also not from CI or a cloud session.
- **Simple first** (P2): price, hour and transfer weights are visible; each extra has a default in "Advanced".
- **Robust sources first** (P3), **platform features first** (P4), **untrusted and private data** (P5):
  `steering/project/PRINCIPLES.md`.
- All times are timezone-aware: store UTC and the original offset. Money is `Decimal`, never `float`.
- The score is computed at query time from the active profile; derived values (duration, transfers) at ingest.

@framework/CLAUDE.md
@docs/LEARNINGS.md
