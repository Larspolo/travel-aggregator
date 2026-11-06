# travel-aggregator

A self-hosted web app that collects the train, bus and flight offers that you see on travel sites, and ranks them by
your own "effective cost": price plus your value of time, transfers, night travel and door-to-door access.

You search on bahn.de, NS International, Flixbus or a flight site as usual. A Tampermonkey userscript reads the
results that the page shows and sends them to your server. The trip page then shows all offers of all sites in one
ranked list, with a breakdown of each score ("€90 price + €62 time + €30 transfers = €182").

> **Status: early development.** The status of each feature is in
> [`steering/project/ROADMAP.md`](steering/project/ROADMAP.md). This README describes only what works on `main`.

## How it works

```
[Browser + Tampermonkey userscripts] --HTTPS POST (JSON, API token)--> [Ingest API]
                                                                            |
                                                                       [PostgreSQL]
                                                                            |
                                                         [Web UI: trips, ranked offers]
```

- **Passive capture only.** The userscripts read only the responses that the page loaded for your own search. The
  app sends no request to a travel site: no crawler, no replayed request, no scheduled fetch.
- **No personal data.** The app does not store login data, cookies, passenger names or payment data.
- The full specification: [`docs/SPEC.md`](docs/SPEC.md).

## Run it on your computer

You need Docker with Docker Compose.

```bash
cp .env.example .env    # then set POSTGRES_PASSWORD (also in DATABASE_URL) and SECRET_KEY
docker compose up --build
```

Open `http://localhost:8000/api/health`. It answers `{"status": "ok", "commit": "dev"}`. Set `APP_PORT` in `.env`
to use another port.

## Run it on a server

Each green build of `main` becomes the image `ghcr.io/larspolo/travel-aggregator:preview`.
[`deploy/preview/`](deploy/preview/) runs it behind Traefik, with its own database and a scoped watchtower that
installs each new image within 5 minutes.

1. Copy `deploy/preview/docker-compose.yml` and `deploy/preview/.env.example` to a folder on the server. Rename the
   second file to `.env`.
2. In `.env`, set random values for `POSTGRES_PASSWORD` (also in `DATABASE_URL`) and `SECRET_KEY`
   (`openssl rand -hex 24`), and set `TRAVEL_AUTH_USERS` to a basic auth line
   (`docker run --rm httpd:2.4-alpine htpasswd -nbB USER 'PASSWORD'`, in single quotes).
3. Change the host name `travel-preview.larspolo.nl` in the compose file to your own.
4. `docker compose up -d`.

The pages need the basic auth login until the app has its own login. `/api` needs no basic auth: the API has its
own tokens. `GET /api/health` shows the commit that runs.

The preview is for test data. A release image for your real data follows later (roadmap item `host:deploy`).

## Configuration

| Variable | Use |
|---|---|
| `DATABASE_URL` | The PostgreSQL URL of the app, for example `postgresql+psycopg://travel:PASSWORD@db:5432/travel` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | The settings of the `db` container |
| `SECRET_KEY` | The session key of the login (a long random value) |
| `APP_PORT` | The port on your computer for `docker compose up` (default `8000`) |
| `TRAVEL_AUTH_USERS` | Server only: the Traefik basic auth line for the pages |
| `GIT_SHA` | Set by the image build: the commit that `/api/health` shows |

## API

| Method and path | Use |
|---|---|
| `GET /api/health` | `{"status": "ok", "commit": "<commit of the image>"}` |

## Development

You need Python 3.12 and PostgreSQL 16 for the tests.

```bash
python3 -m pip install -r requirements-dev.txt
ruff check .
python3 -m pytest -n auto
```

The code: `app/` (FastAPI), `tests/` (pytest). The planned layout is in [`CLAUDE.md`](CLAUDE.md), section "Code map".

## How the project is built

AI agents (Claude Code) build this project from the roadmap, with the agent system in `framework/`. They take the
tickets (GitHub issues), make a pull request for each ticket and merge it when CI is green. The owner steers with
issues, [`steering/project/PRINCIPLES.md`](steering/project/PRINCIPLES.md) and the roadmap.

## License

GPL-3.0. See [`LICENSE`](LICENSE).
