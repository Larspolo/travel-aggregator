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

1. Make the settings file: `cp .env.example .env`. Set `POSTGRES_PASSWORD` (also in `DATABASE_URL`) and
   `SECRET_KEY` to random values (`openssl rand -hex 24`).
2. Make the hash of your login password and put it in `.env` as `OWNER_PASSWORD_HASH`, in single quotes:

   ```bash
   docker compose build app && docker compose run --rm --no-deps --entrypoint python app -m app.auth 'YOUR-PASSWORD'
   ```

3. Start the app. It runs the database migrations first:

   ```bash
   docker compose up --build -d
   ```

4. Make an API token for your browser (the token shows only once; `list` and `revoke ID` also work):

   ```bash
   docker compose exec app python -m app.tokens create laptop
   ```

5. Make a trip and send an offer to it (the userscripts do this later):

   ```bash
   TOKEN=...   # the token of step 4
   curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"title": "Amsterdam – Zürich"}' http://localhost:8000/api/trips
   curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{
     "trip_id": 1, "source": "manual", "captured_at": "2026-11-06T10:00:00Z",
     "offers": [{"price_amount": "89.90", "price_currency": "EUR", "fare_name": "Sparpreis",
       "legs": [{"mode": "train", "carrier": "DB", "service_no": "ICE 105",
         "from_name": "Amsterdam Centraal", "to_name": "Basel SBB",
         "depart_at": "2026-12-20T07:34:00+01:00", "arrive_at": "2026-12-20T14:02:00+01:00"}]}]
   }' http://localhost:8000/api/ingest
   ```

6. Log in at `http://localhost:8000/login`. The trips list opens; click a trip to see its offers.

`http://localhost:8000/api/health` shows `{"status": "ok", "commit": "dev"}`. Set `APP_PORT` in `.env` to use
another port.

## Run it on a server

Each green build of `main` becomes the image `ghcr.io/larspolo/travel-aggregator:preview`.
[`deploy/preview/`](deploy/preview/) runs it behind Traefik, with its own database and a scoped watchtower that
installs each new image within 5 minutes.

1. Copy `deploy/preview/docker-compose.yml` and `deploy/preview/.env.example` to a folder on the server. Rename the
   second file to `.env`.
2. In `.env`, set random values for `POSTGRES_PASSWORD` (also in `DATABASE_URL`) and `SECRET_KEY`
   (`openssl rand -hex 24`). Set `TRAVEL_AUTH_USERS` to a basic auth line
   (`docker run --rm httpd:2.4-alpine htpasswd -nbB USER 'PASSWORD'`) and `OWNER_PASSWORD_HASH` to the hash of your
   login password (`docker run --rm --entrypoint python ghcr.io/larspolo/travel-aggregator:preview -m app.auth 'PASSWORD'`),
   both in single quotes.
3. Change the host name `travel-preview.larspolo.nl` in the compose file to your own.
4. `docker compose up -d`, then make an API token: `docker compose exec app python -m app.tokens create laptop`.

The pages need the basic auth login and then the login of the app. `/api` needs no basic auth: the API has its own
tokens. `GET /api/health` shows the commit that runs.

The preview is for test data.

### The production instance

For your real data, use the release images. [`deploy/production/`](deploy/production/) runs the image
`ghcr.io/larspolo/travel-aggregator:latest`, with its own database volume and its own scoped watchtower. The watchtower
checks the registry every 5 minutes. `:latest` changes only when an epic closes, so the production instance does not
follow each merge.

1. Copy `deploy/production/docker-compose.yml` and `deploy/production/.env.example` to a folder on the server. Rename the
   second file to `.env`, and set the values as in the preview steps above (`POSTGRES_PASSWORD`, `DATABASE_URL`,
   `SECRET_KEY`, `OWNER_PASSWORD_HASH`). The production file has no basic auth: the app has its own login.
2. Put a reverse proxy in front of `127.0.0.1:8000`. The app is published on localhost only. Pick one:
   - Traefik: copy `deploy/traefik/docker-compose.override.yml` to `deploy/production/docker-compose.override.yml`, and
     change the host name `travel.example.com` in it. Traefik must run on the external network `proxy`.
   - Caddy: copy `deploy/caddy/Caddyfile` to `/etc/caddy/Caddyfile` and change the host name. Caddy gets the HTTPS
     certificate itself.
   - nginx: copy `deploy/nginx/travel-aggregator.conf` to `/etc/nginx/conf.d/`, change the host name and the
     certificate paths.
   All three examples set `X-Forwarded-Proto` and forward `/api` too. The app trusts these headers.
3. `docker compose up -d`, then make an API token: `docker compose exec app python -m app.tokens create laptop`.

Before each migration that changes data, the container writes a `pg_dump` backup to the volume `backups-production`
(mounted at `/backups`). If the backup fails, the migration and the start of the app stop.

Each closed epic makes a release: the workflow `.github/workflows/release.yml` pushes the git tag `vX.Y.Z` and the
images `:vX.Y.Z` and `:latest`. `GET /api/health` shows the commit that runs.

## Configuration

| Variable | Use |
|---|---|
| `DATABASE_URL` | The PostgreSQL URL of the app, for example `postgresql+psycopg://travel:PASSWORD@db:5432/travel` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | The settings of the `db` container |
| `SECRET_KEY` | The key that signs the login session (a long random value; with none, each restart ends the sessions) |
| `OWNER_PASSWORD_HASH` | The hash of the login password: `python -m app.auth 'PASSWORD'` |
| `APP_PORT` | The port on your computer for `docker compose up` (default `8000`) |
| `TRAVEL_AUTH_USERS` | Server only: the Traefik basic auth line for the pages |
| `GIT_SHA` | Set by the image build: the commit that `/api/health` shows |

## API

| Method and path | Use |
|---|---|
| `GET /api/health` | `{"status": "ok", "commit": "<commit of the image>"}`. No token. |
| `GET /api/trips` | The trips, newest first; `?status=active` filters them |
| `POST /api/trips` | Make a trip: `{"title": "...", "origin_text", "destination_text", "date_from", "date_to", "travelers"}` |
| `POST /api/ingest` | Captured offers for a trip (body: [`docs/SPEC.md`](docs/SPEC.md) section 5). Answers `{"created": n, "updated": n, "unchanged": n}` |

`POST /api/ingest` stores each offer by its journey. The same journey sent twice gives one itinerary. A changed price
adds a price row; the same price adds none and counts as `unchanged`. Each offer is stored in its own transaction.

All routes but `/api/health` need `Authorization: Bearer <token>` (`python -m app.tokens create NAME`). Bodies are
limited to 5 MB.

## Pages

| Path | Use |
|---|---|
| `/login` | The login form: the password of `OWNER_PASSWORD_HASH`. The session is signed with `SECRET_KEY` |
| `/logout` | Ends the login session |
| `/` | The list of your trips, with a link to each trip |
| `/trips/new` | The form to make a trip |
| `/trips/{id}/edit` | The form to change a trip |
| `/trips/{id}` | The offers of a trip, ranked by effective cost, with the two sliders |
| `/tokens` | The API tokens: create a token (shown once, with the settings for the userscripts) and revoke a token |
| `/places` | The access and egress places: add a place (text, kind, minutes, cost) or delete one |

All pages but `/login` need the login. Each form that changes data sends a CSRF token: a form without a correct token
gets the answer 403.

## Userscript panel

Each userscript shows a small panel at the bottom right of the travel site. The panel shows `Captured N offers → sent ✓`
when the offers reached your server, or an error message.

- **Trip.** The dropdown chooses the trip that receives the offers. `+ new trip` makes a trip with the title that you
  type. The app remembers the chosen trip.
- **Auto-send.** This check box is on by default. With it on, the offers are sent at once. With it off, the offers wait
  in the queue until you press Send.
- **Settings.** Set the server URL and the API token once, in the Tampermonkey menu (`Set server URL`, `Set API token`).
  Make the token on the `/tokens` page.
- **Not sent.** When a send fails, the offers stay in the queue. With auto-send on, the userscript sends them again
  later.

## Ranking

The trip page `/trips/{id}` ranks the offers by effective cost, lowest first:

```
effective cost = price + hours × hour markup + transfers × transfer markup + door-to-door parts
```

The door-to-door parts are described below.

Each row shows the breakdown of its cost, for example `€90 price + €62 time + €30 transfers = €182`. A part that is
0 is not shown. Two sliders above the list set the hour markup (default €15) and the transfer markup (default €10),
from €0 to €100. When you move a slider, the list ranks again at once.
The values are not stored: a link such as `/trips/1?hour_markup=20&transfer_markup=5` opens the page with them.

### Door-to-door

The effective cost also counts the time and cost outside the vehicle. The breakdown shows each part on its own.

- **Access and egress places.** `/places` lists the places that you set. A place has a text, a kind, minutes and a cost.
  Kind `access` is the way from the place to the first station; kind `egress` is the way from the last station to the
  place. A leg matches a place when its station name has the same text (case and outer spaces do not count). An offer
  with a matching access place adds the parts `access time` (minutes × hour markup) and `access cost`. An offer with a
  matching egress place adds `egress time` and `egress cost`. An offer with no matching place adds nothing.
- **Airport time and baggage (flights).** An offer with a flight leg adds two parts. `airport time` is the minutes before
  departure plus the minutes after landing, at the hour markup. `baggage` is the baggage fee.
  The **Advanced** section under the sliders sets them. The defaults are 120 minutes before departure, 30 minutes after
  landing and a baggage fee of €0. A value of 0 removes that part from the ranking.

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
