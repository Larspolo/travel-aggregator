# travel-aggregator

A self-hosted web app that collects the train, bus and flight offers that you see on travel sites, and ranks them by
your own "effective cost": price plus your value of time, transfers, night travel and door-to-door access.

You search on bahn.de, NS International, Flixbus, SNCF Connect or a flight site as usual. A Tampermonkey userscript reads the
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
- **No personal data.** The app does not store cookies of travel sites, passenger names or payment data. It keeps the time, IP address and browser of your last 200 logins and failed logins (see [Recent logins](#recent-logins)).
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
   (`openssl rand -hex 24`). Set `OWNER_PASSWORD_HASH` to the hash of your login password (`docker run --rm --entrypoint python ghcr.io/larspolo/travel-aggregator:preview -m app.auth 'PASSWORD'`),
   in single quotes.
3. Change the host name `travel-preview.larspolo.nl` in the compose file to your own.
4. `docker compose up -d`, then make an API token: `docker compose exec app python -m app.tokens create laptop`.

The pages need the login of the app. `/api` needs no basic auth: the API has its own
tokens. `GET /api/health` shows the commit that runs.

The preview is for test data.

### The production instance

For your real data, use the release images. [`deploy/production/`](deploy/production/) runs the image
`ghcr.io/larspolo/travel-aggregator:latest`, with its own database volume and its own scoped watchtower. `:latest`
changes only when an epic closes, so the production instance does not follow each merge.

Follow these steps from an empty server to a first captured offer. Do the check after each step before you continue.

#### What the server needs

- Docker with the compose plugin. Check: `docker compose version` shows a version.
- A DNS name (for example `travel.example.com`) that points to the server. Check: `dig +short travel.example.com`
  shows the IP address of the server.
- The ports 80 and 443 open from the internet (the reverse proxy gets the HTTPS certificate on them).

#### 1. Install

Copy `deploy/production/docker-compose.yml` and `deploy/production/.env.example` to a folder on the server. Rename
the second file to `.env`. In `.env`, set random values for `POSTGRES_PASSWORD` (also in `DATABASE_URL`) and
`SECRET_KEY` (`openssl rand -hex 24`). Set `OWNER_PASSWORD_HASH` to the hash of your login password
(`docker run --rm --entrypoint python ghcr.io/larspolo/travel-aggregator:latest -m app.auth 'PASSWORD'`), in single
quotes. Then start it: `docker compose up -d`.

Check: `curl http://127.0.0.1:8000/api/health` on the server shows `"status"` and the commit that runs. The app is
published on localhost only.

#### 2. Reverse proxy with HTTPS

Put a reverse proxy in front of `127.0.0.1:8000`. Pick one:

- Traefik: copy `deploy/traefik/docker-compose.override.yml` to `deploy/production/docker-compose.override.yml`, and
  change the host name `travel.example.com` in it. Traefik must run on the external network `proxy`.
- Caddy: copy `deploy/caddy/Caddyfile` to `/etc/caddy/Caddyfile` and change the host name. Caddy gets the HTTPS
  certificate itself.
- nginx: copy `deploy/nginx/travel-aggregator.conf` to `/etc/nginx/conf.d/`, change the host name and the
  certificate paths.

All three examples set `X-Forwarded-Proto` and forward `/api` too. The app trusts these headers.

Check: `curl https://<host>/api/health` from your computer shows the same answer as in step 1.

#### 3. Log in

Open `https://<host>/` in your browser and log in with the password of step 1.

Check: the page shows the trips list ("You have no trips." on a new server).

#### 4. Make an API token

Open the `/tokens` page, type a name (for example `laptop`) and make a token. Copy the token: the page shows it only
once. (On the server, `docker compose exec app python -m app.tokens create laptop` does the same.)

You can also type an end date (optional). The token stops working at 00:00 UTC of the day after that date, so
the last day is the chosen date. A blank end date gives no end date. The column "Ends" shows the date, or "never".
After the end date, the token shows the chip "ended". The API then answers `401`, as for a bad token. A date in
the past is an error: no token is made. A token that was not used for 90 days shows the chip "not used for 90 days".

Check: the token is in the list on the `/tokens` page.

#### 5. Install the userscript

Install the browser extension Tampermonkey. On the `/tokens` page, open the install link of each userscript
(the `Install` link of the list "Userscripts"). Tampermonkey shows the install dialog: confirm it.

The userscript knows its server: the address of the page that installed it is the default server URL. You do not
need to set a server URL. The userscript updates itself: Tampermonkey checks the server for a new version of the
script, so you do not install the userscript again after an update.

In the Tampermonkey menu, use `Set API token` (the token of step 4). Use `Set server URL` only when the server
differs from the address that installed the userscript.

Check: the Tampermonkey dashboard shows the script as on.

The repository also has the userscripts (`userscripts/bahn.user.js`, `userscripts/ns.user.js`, `userscripts/flixbus.user.js`, `userscripts/sncf.user.js`, `userscripts/kiwi.user.js`). To install from the
repository instead, add the file as a new script in Tampermonkey and set the server URL (`https://<host>`).

#### 6. Capture a first offer

On the trips page, make a trip. On bahn.de, choose that trip in the panel and search for a connection.

Check: the panel shows `Captured N offers → sent ✓`, and the trip page shows the offers.

#### 7. Backup and restore

Before each migration that changes data, the container writes a `pg_dump` backup to the volume `backups-production`
(mounted at `/backups`). If the backup fails, the migration and the start of the app stop. Make a backup at any time,
and restore one:

```bash
make backup                                   # or: docker compose exec app python -m app.backup --now
make restore FILE=/backups/<file>.dump        # or: docker compose exec app python -m app.restore /backups/<file>.dump
```

A restore gives back the trips, the offers and the price history of the dump. It runs in one transaction: if the file
is missing or bad, the command stops with an error and the database does not change. The backups hold private data
(your trips and offers). They stay in the volume: copy them only to a place that you trust.

The service `backup` (it starts with `docker compose up -d`) also writes a daily dump to the same volume: a file
`<UTC time>-daily.dump`. It writes a dump when the newest daily dump is older than `BACKUP_INTERVAL_HOURS` (default 24).
If a dump fails, the service retries after one hour. Only the newest `BACKUP_KEEP` daily dumps stay (default 14); the
older daily dumps are deleted. The manual dumps (`make backup`) and the dumps before a migration stay always.

The settings page has the section "Backups". It shows the time (UTC) and the size of the newest backup. It shows a
warning when the newest backup is older than 48 hours, or "No backup yet." when there is none.

After each daily dump, the service reads the new file again with `pg_restore --list`. This shows that the file can
be read. The card "Backups" on the settings page shows the result of this check:

- "Checked: N tables": the check passed. N is the number of tables in the dump.
- "Check failed": the check of the newest daily dump failed. The card shows the time (UTC) and the error.
- "Not checked yet": no daily dump is checked yet.

A failed check renames the file to `<UTC time>-daily.dump.failed`. The file stays in the volume, and only the newest
`*.failed` file stays. The service sends "Backup failed" and tries again after one hour.

Check: `docker compose exec app ls /backups` shows the new `.dump` file (a manual dump, or a `-daily.dump` file of the
service `backup`).

##### Backup messages

The app can send a message about the backups by the channel that you choose on the messages settings page
(`/settings/messages`, the same channel as the price-drop messages, see "Messages outside the app"). With the
channel `none`, no message is sent.

- "Send a test message": the button on the messages settings page sends one test message by the active channel. Use it
  to check the channel. It needs a channel first; otherwise the page says "Select a channel first".
- "Backup failed": the service `backup` could not write a daily dump. It sends at most one message in 24 hours while the
  dumps fail.
- "Backup works again": the next daily dump works after a "Backup failed" message. It is sent once.
- "No backup for N days.": the newest backup is older than 48 hours. The app checks this when a userscript sends offers,
  and it sends the message at most once in 24 hours. When there is no backup at all, the text is "No backup yet.".

##### Metrics for Prometheus

The app has a metrics endpoint `GET /metrics` for a Prometheus server. It uses its own token, not an API token. To make the
token, open the settings page and use the card "Metrics token", then press "Make a new token". The token shows only once:
copy it then. "Stop the token" turns the endpoint off. A new token replaces the old one, and the old one stops at once.
A request without the token, or with a wrong token, gets `401`.

The endpoint shows these metrics (the text format of Prometheus):

- `travel_trips`: the count of trips, also the archived trips.
- `travel_offers`: the count of itineraries.
- `travel_captures_total` (per `source`): the count of captures.
- `travel_capture_failures_total` (per `source`): the count of failed captures.
- `travel_last_good_capture_age_seconds` (per `source`): the seconds since the last good capture of the source.
- `travel_backup_age_seconds`: the seconds since the newest backup. Only when there is a backup.
- `travel_backup_size_bytes`: the size of the newest backup in bytes. Only when there is a backup.
- `travel_backup_check_ok`: `1` when the check of the newest backup read the dump, else `0`. Only when there is a check result.

Store the token in a file that only Prometheus can read, for example `/etc/prometheus/travel-metrics-token`. Then add this
job to the Prometheus configuration (replace `<host>` with your host):

```yaml
scrape_configs:
  - job_name: travel-aggregator
    metrics_path: /metrics
    scheme: https
    authorization:
      type: Bearer
      credentials_file: /etc/prometheus/travel-metrics-token
    static_configs:
      - targets: ['<host>']
```

Check: `curl -H "Authorization: Bearer <token>" https://<host>/metrics` shows the lines `travel_trips` and `travel_offers`.

#### 8. Update

The scoped watchtower checks the registry every 5 minutes and installs each new `:latest` image. Each closed epic
makes a release: the workflow `.github/workflows/release.yml` pushes the git tag `vX.Y.Z` and the images `:vX.Y.Z` and
`:latest`. To update at once: `docker compose pull && docker compose up -d`.

Check: `curl https://<host>/api/health` shows the commit of the new release.

## Configuration

| Variable | Use |
|---|---|
| `DATABASE_URL` | The PostgreSQL URL of the app, for example `postgresql+psycopg://travel:PASSWORD@db:5432/travel` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | The settings of the `db` container |
| `SECRET_KEY` | The key that signs the login session (a long random value; with none, each restart ends the sessions) |
| `OWNER_PASSWORD_HASH` | The hash of the login password: `python -m app.auth 'PASSWORD'` |
| `APP_PORT` | The port on your computer for `docker compose up` (default `8000`) |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | The key pair of Web Push (channel `webpush`). Make it with `python3 -m app.notify`, which prints both lines. Keep the private key secret |
| `VAPID_SUBJECT` | The contact of the sender for the push services: a `mailto:` address, for example `mailto:you@example.com` |
| `SMTP_HOST`, `SMTP_PORT` | The SMTP server of the e-mail channel. Port `587` uses STARTTLS, port `465` uses SSL (default port `587`) |
| `SMTP_USER`, `SMTP_PASSWORD` | The login of the SMTP server. The password stays in the environment, never in the database |
| `SMTP_FROM` | The sender address of the e-mail |
| `PASSKEY_ORIGIN` | The origin of the passkeys, for example `https://travel.example.com`. Empty: the origin of the request (the reverse proxy must send `X-Forwarded-Proto` and `Host`) |
| `BACKUP_INTERVAL_HOURS` | The hours between two daily backups of the service `backup` (default `24`) |
| `BACKUP_KEEP` | The number of daily dumps that stay; the older ones are deleted (default `14`, at least `1`) |
| `PASSKEY_ORIGIN` | The origin of the passkeys, for example `https://travel.example.com` (see "Passkeys"). Empty: the origin of the request. Set it when the reverse proxy does not send `X-Forwarded-Proto` and `Host` |

To turn on Web Push, run `python3 -m app.notify` once. It prints `VAPID_PUBLIC_KEY=...` and `VAPID_PRIVATE_KEY=...`.
Put both lines and a `VAPID_SUBJECT` in the `.env` file, then restart the app. The settings page then shows the
Web Push buttons. Without these three variables the channel `webpush` is not available.

The image build sets `GIT_SHA` (a build argument of the `Dockerfile`, not a setting): the commit that
`/api/health` shows.

## API

| Method and path | Use |
|---|---|
| `GET /api/health` | `{"status": "ok", "commit": "<commit of the image>", "built": "<build time of the image>"}`. No token. |
| `GET /api/trips` | The trips, newest first; `?status=planning` (or `booked`, `archived`) shows only the trips of that status |
| `POST /api/trips` | Make a trip: `{"title": "...", "origin_text", "destination_text", "date_from", "date_to", "travelers"}` |
| `POST /api/ingest` | Captured offers for a trip (body: [`docs/SPEC.md`](docs/SPEC.md) section 5). Answers `{"created": n, "updated": n, "unchanged": n}` and the field `warning`: the text of the trip warning, or `null` (see "Trip warning of a capture") |
| `POST /api/silent` | A results page with no offers seen: `{"source", "page_url", "seen_at", "script_version"}`. The app stores these four fields only (see "No offers seen on a results page"). Answers `{"id": n}` |

The body can have the field `auto_trip` (`true` or `false`, default `false`). With `true`, the app stores the offers in the
planning trip that matches them when `trip_id` does not match, as described in "Auto-select trip" under "Userscript
panel". The answer then also has `trip_id` and `trip_title`: the trip that got the offers. When no trip matches, the
answer has the field `suggestion`: an object with `title`, `origin_text`, `destination_text` and `date_from` for a new
trip, built from the offers. Else `suggestion` is `null`.

The answer also has the field `best`: the best offer of the trip by its effective cost, as an object with `total`,
`price`, `currency`, `summary` and `new`. Money is a string, for example `"182.00"`. `new` is `true` when this capture
made the best offer better (or gave the first one). `best` is `null` when the trip has no offer.

`POST /api/ingest` stores each offer by its journey. The same journey sent twice gives one itinerary. A changed price
adds a price row; the same price adds none and counts as `unchanged`. Each offer is stored in its own transaction.

The body can also have the field `raw`: the original response of the travel site, as sent by the userscript. The app
stores it as a capture, so a later parser fix can run again on it (see "Reparse a capture" below). A body with `raw`
and no `offers` is valid. The app reports a connection that the parser cannot read in `errors`.

An offer can have the field `travel_class`: `first` (1st class), `standard` (2nd class) or no field (not set). A fare with the class `first` gets the badge "1st" and the part `1st class` of "Risk" under "Ranking".

Each leg of an offer can have the field `ticket`: a whole number from 1 to 20 for the ticket of the leg. When the number
changes between two legs, the fare counts one self-transfer. A leg with no `ticket` keeps the ticket of the leg before
it. See "Risk" under "Ranking".

An offer of a flight can have the fields `checked_bags_included` (a whole number from 0 to 9: the checked bags that the fare includes) and `checked_bag_price` (a money value: the price of the first checked bag, in the currency of the offer). A fare with `checked_bags_included` of at least 1 gets the part `baggage (included)`; a fare with `checked_bag_price` gets the part `baggage` at that price in EUR. See "Airport time and baggage (flights)" under "Ranking". A field with no value is not set.

All routes but `/api/health` need `Authorization: Bearer <token>` (`python -m app.tokens create NAME`). Bodies are
limited to 5 MB. A token with an end date is refused after that date (see step 4 of the setup).

The API has two limits:

- **Requests.** A token may send 120 requests in 60 seconds. A request over this limit gets `429` with the header
  `Retry-After` (the seconds to wait).
- **Bad tokens.** An address that sends 20 bad tokens in 15 minutes gets `429` with `Retry-After` for 15 minutes. This
  also applies to a valid token from that address. The limit is per address, so one address cannot lock the API for
  the others.

The counts of the request limit live in the memory of the app: a restart of the app resets them.

## Pages

| Path | Use |
|---|---|
| `/login` | The login form: the password of `OWNER_PASSWORD_HASH`. With the second login step on, a code page follows (see "Second login step" below). The session is signed with `SECRET_KEY` |
| `/logout` | Ends the login session |
| `/` | The list of your trips that are not archived, with a link to each trip. `/?archived=1` shows the archived trips |
| `/trips/new` | The form to make a trip |
| `/trips/{id}/edit` | The form to change a trip |
| `/trips/{id}/delete` | The confirm page to delete a trip |
| `/trips/{id}` | The offers of a trip, ranked by effective cost, with the two sliders |
| `/trips/{id}/compare` | 2 to 4 offers of a trip side by side, with the best value of each line marked (see below) |
| `/tokens` | The API tokens: create a token (shown once, with the settings for the userscripts; optional end date) and revoke a token |
| `/places` | The access and egress places: add a place (text, kind, minutes, cost) or delete one |
| `/rates` | The exchange rates: store the value in EUR of a currency, or delete a rate (see "Exchange rates" below) |
| `/fees` | The booking fees: store the fee in EUR of a source, or set it to 0 to remove it (see "Booking fees" below) |
| `/profiles` | The score profiles: list the profiles, set the default, rename a profile or delete a profile. `/profiles/new` makes a profile with no trip, and `/profiles/{id}` edits its weights |
| `/pinned` | The pinned offers of the trips in planning, in the order of departure (see "Pinned offers" below) |
| `/captures` | The captures of all trips, newest first, with the trip of each capture. The link "Captures" at the top of each page opens it |
| `/trips/{id}/captures` | The captures of a trip, with the parse result and the action "reparse capture" (see below). The link "Only failed captures" shows only the failed captures (`?failed=1`); "Show all captures" shows all again |
| `/trips/{id}/itineraries/{id}/history` | The price history of an offer: a chart per fare, with a table of the prices, the newest first |
| `/settings` | The capture retention period (see below), the size of the data (card "Storage"), the card "Sessions" with the button "Log out on all other devices" (see below), the channel of the price-drop messages with its ntfy topic URL and e-mail address (see "Messages outside the app"), and "Turn on push on this device" and "Remove push from this device" for Web Push |
| `/sw.js` | The service worker of Web Push. It needs no login |
| `POST /settings/push` | Subscribes the browser that sends the form to Web Push. Used by the settings page (CSRF token needed) |
| `POST /settings/push/delete` | Removes the push subscription of the browser that sends it (CSRF token needed) |

All pages but `/login` need the login. Each form that changes data sends a CSRF token: a form without a correct token
gets the answer 403.

Each page has the same app bar at the top: the name "travel-aggregator" links to the trips list. The links Trips, Upcoming, Pinned, Captures,
Profiles, Places and Settings follow it, and "Log out" ends the login session. The current page is marked in the bar.
Most pages start with a page header: the title, a subtitle, and a link such as "Back to the trip" where one applies. Its buttons
sit at the right side. The content is in cards, each with an optional title. A list with no item shows an empty state:
a short text and, where it helps, a button to the next step (for example "Install the userscripts" on an empty captures page).

### Log out on all other devices

The card "Sessions" on the settings page (`/settings`) has the button "Log out on all other devices". The button ends the
login on all other browsers and devices. This browser stays logged in. Use it when you lost a device or you used a
computer that is not yours.

The saved copy of the Upcoming page (see "Upcoming journeys") goes from the other devices at their next online visit to
the app. Until then, a device with no network can still show it. The API tokens and the share and calendar links have
their own "Revoke": on `/tokens` for the API tokens, on the trip page for a share link, and on the Upcoming page for a calendar link.
The button does not revoke them.

### Recent logins

The card "Recent logins" on the settings page (`/settings`) lists the last 20 logins and failed logins, newest first.
Each row shows the date and time (UTC), the IP address, the browser, and the result:

- "login": a login with the password.
- "login with code": a login with the password and a code of the authenticator app.
- "recovery code": a login with a recovery code.
- "login with passkey": a login with a passkey (see "Passkeys").
- "failed", "failed (code)" and "failed (passkey)": a wrong password, a wrong code, or a passkey that is not correct
  or not known. These rows are marked in orange.

Check this card often. If you see a login or a failed login that you did not make, act at once:

1. Make a new password hash with `python -m app.auth 'NEW_PASSWORD'` (the step 2 of "Run it on your computer" shows the Docker command).
   Put the new hash in `.env` as `OWNER_PASSWORD_HASH`, in single quotes, and restart the app.
2. Click "Log out on all other devices" in the card "Sessions" (see below). This ends every other login.
3. Turn on the second login step (see below). Then a password alone is not enough to log in.

### Second login step

The card "Second login step" on the settings page (`/settings`) turns on a code of your authenticator app. Its state
shows "On" or "Off". With the step off, the login asks only for the password.

To turn it on:

1. Click "Turn on". The page shows a QR code, the key as text and the link "Open in the authenticator app".
2. Add the key to your authenticator app: scan the QR code or type the key.
3. Type the code of the app in "Code from the app" and click "Confirm". The page shows "On" and the ten recovery codes.
   Save these codes: each one logs in one time. The page shows them only once.

With the step on, the login asks for the code after the password: the page "Log in" shows the field "Code from the app".
A recovery code also works in this field. A used recovery code stops working. The count "Recovery codes left" on the settings page
shows how many are left.

To get ten new recovery codes, type a current code of the app in the field under "New recovery codes" and click the button.
The old codes stop working. To turn the step off, type a current code of the app in the field under "Turn off" and click "Turn off".

If you lost the app and no recovery code is left, turn the step off on the server with this command. It needs no code, and it
ends the login on all other devices:

```
docker compose exec app python3 -m app.totp off
```

The command prints "The second login step is off." The API tokens need no code: they work as before.

### Passkeys

A passkey logs you in with the lock of your device (a fingerprint, the face or the PIN), with no password and no code
of the authenticator app. The password login stays: the page "Log in" always shows the password field.

To add a passkey:

1. Open the card "Passkeys" on the settings page (`/settings`).
2. Type a name in "Name of the device", for example "Laptop", and click "Add a passkey".
3. Confirm with the lock of your device. The page shows the new passkey in the list.

Each row of the list shows the name, the date it was added, and the date of the last use ("never used" before the first
login). Add one passkey on each device that you use.

When one or more passkeys are stored, the page "Log in" shows the button "Log in with a passkey". Click it and
confirm with the lock of your device. A passkey login does not ask for the code of the second login step. A passkey
that is not correct counts as a failed login: the card "Recent logins" shows "failed (passkey)".

To remove a passkey, click "Remove" in its row. It stops working at once. Remove the passkey of a lost device, and then
click "Log out on all other devices" (see above).

A passkey works only on the address where you added it. The browser accepts passkeys only on `https://` or on
`localhost`. The app takes the address from the request: behind a reverse proxy, the proxy must send `X-Forwarded-Proto`
and `Host`. If it does not, set `PASSKEY_ORIGIN` in `.env` to the address of the app, for example
`PASSKEY_ORIGIN=https://travel.example.com`, and restart the app. If you change the address of the app later, add
the passkeys again.

### Use a phone

All pages work at a phone width of 390 px. No page scrolls sideways.
At a width of 640 px or less, the links of the app bar move into one "Menu" button at the top right. Tap it to open
the list of the same pages; each entry is at least 44 px high.
A wide table scrolls sideways in its own box: this is the trip table and the compare table.
The sliders, the filter fields and the buttons of the trip page are large enough for a finger: each is at least 40 px high.
The fields under "Advanced" on the trip page show in two columns, also at a phone width.

To add the app to the home screen of a phone, open it in the browser and use "Add to Home Screen" (in Safari on an
iPhone: tap Share, then "Add to Home Screen"). The app then has its name, its icon and its colours from a web app
manifest (`/manifest.webmanifest`). Each page links this manifest. On an iPhone or iPad, Web Push works only from the
app on the home screen, not in a browser tab (see "Messages outside the app").

### Use the keyboard and a screen reader

Each page works with the keyboard only. Tab moves to the next control and Shift+Tab to the previous one. Each control
that has the focus shows a visible focus mark.
Enter opens a menu (the "Menu" button at a phone width, and "More" at a desktop width). Escape closes an open menu and
puts the focus back on its button. On the trip page, Enter on "Legs and fares" opens the legs and fares of a row.
On a weight slider, the arrow keys change the value by one step, and the list of offers ranks again at once.

The pages are checked with axe-core, an automated accessibility tester, at a width of 1280 px and at 390 px. The check
fails on each new finding of the rules "serious" and "critical". Known findings are listed in the test, and each one is
removed when it is fixed.

### Compare offers in the trip table

The table of `/trips/{id}` has one row per journey. The same train from bahn.de and NS International shows once, with the fares of both sources in its "Legs and fares". Two offers are one journey when their modes and service numbers are the same, and their first departure and last arrival are at the same UTC time (the carrier and the times of the legs between do not count). The pin, hide, booked, note and price history are per journey.
Each row shows a mode icon for each mode of its legs: 🚆 train, 🚌 bus and ✈️ flight.
Tick the boxes of the rows, and a bar shows at the bottom of the table with the count. Its buttons work on the ticked rows: "Compare" opens the compare page, "Hide" hides all the ticked offers and "Pin" pins all of them. Each button also works with the keyboard and on a phone. When the filters hide offers, the line "Filters hide N of M offers" has the button "Hide all N": it hides each offer that the filters hide, so they stay hidden when you remove the filters.

A fare of the 1st class shows the badge "1st" after its name. The badge shows in the fare list of each row and on the compare page.
A fare that the site priced with a discount card shows the card name after its name, for example "BahnCard 50". No name shows when the capture does not tell the cards, or when the fare name already has the card name.
When the current fares of a trip use different sets of discount cards, the trip page shows the warning "These fares use different discount cards: BahnCard 50, none", above the table. Each set shows once, joined with " + " when a fare uses more than one card, and "none" is the fare with no card. The warning counts only the fares that show as current: a hidden fare, a departed fare and a fare that a newer search did not show again do not count, and a fare with no known cards does not count.
An arrival on a later calendar day shows a mark "+1 day" (or "+2 days" and so on).
Under the fare name, the age of the newest capture shows, for example "2 h ago".
If the newest capture is older than the stale hours, the row also shows "stale, price may have changed". See "Stale offers".
A fare that a newer search of the same site did not show again, in the departure span of that search, shows the mark "not in the last <source> search". The best offer does not use such a fare. The next search that shows the fare again removes the mark.
A fare whose latest price is implausible shows the chip "check the price" next to its price. A price is implausible when it is €0, or when it is below a fifth or above five times the last usable price of the fare in the same currency. The chip title names the last price, for example "The last price was €39.00". A price of €0 with no earlier price shows the title "A price of 0 cannot be right".
The best offer, the highlights and "Best by profile" do not use a fare with the chip, as long as the row or the trip has a usable fare. A row with only such fares still shows, with the chip and no highlight. The trips list, the target price check and the price-drop messages do not use such a fare either. A later capture with a plausible price removes the chip, and the fare counts again.
Click a column header to sort by it. Click it again to reverse the order.
The Mode and Source lists show only one mode or one source.

The hard filters hide the offers that do not match. A penalty does not hide an offer: it only adds to its cost.
Each filter is a query parameter of `/trips/{id}`. An empty value is no filter.
- `max_transfers`: the most transfers (0 to 10).
- `max_duration_min`: the longest duration in minutes.
- `earliest_depart`: the first leg departs at or after this local time.
- `latest_arrive`: the last leg arrives by this local time, on the day of its departure.
- `exclude_mode`: a mode (train, bus or flight) hides each offer with one of its legs.
- `exclude_carrier`: a carrier hides each offer with one of its legs. A carrier markup (under "Advanced", see "Risk") ranks an offer; an exclusion hides it.
- `hide_stale`: the checkbox "hide stale" above the table hides each stale offer. The badges count only the rows that show.
When the filters hide offers, the line "Filters hide N of M offers" shows above the table. It gives the count of each filter, for example "max transfers 1 hides 3", and each filter name is a link to the page without that filter. The line "Best hidden offer" shows the cheapest offer that the filters hide, with its time, route, source and the filters that hide it. Its "Show it" link opens the page without those filters at that row.
The cheapest, fastest and best-value rows show a badge. The badges use the rows after the filters.
A row with the chip "no faster offer for less" is an offer that no other shown offer beats. No other offer costs the same or less and also needs the same or fewer door-to-door minutes, with one of the two strictly less. Two offers with the same price and the same minutes both get the chip. The mark does not use your weights: a change of a slider does not change it.
The checkbox "only these" in the filters is the query parameter `pareto=true` (in `/trips/{id}`). It hides each shown offer without the mark, so only the marked offers stay. The filter line names it "only marked". It works with the other filters, and the chart below uses the rows after all filters.
The card "Price and door-to-door hours" shows a chart of the shown offers, when there are at least two. The horizontal axis is the door-to-door hours, and the vertical axis is the price (the lowest price at the bottom). Each offer is a point. A filled point is a marked offer, and a line joins the filled points. Hover over a point to see its route, price and hours, and click it to go to its row. Use the chart to see which offers a change of your hour value can bring to the top.
Open "Legs and fares" in a row to see its legs, the transfer times and all fares, each with its link.
The expanded row also shows the price history chart of each fare: one point for each capture of the fare.
The route `/trips/{id}/itineraries/{id}/history` shows the same chart and the table of the prices.
The expanded row also shows a break-even line at the top of "Legs and fares": the hour value at which the row and the best
shown row have the same effective cost. For example, `1 h 20 min faster, €3.00 more than the best: better above €12.50/h (yours: €10/h)`.
"Yours" is your hour markup. "Better above €X/h" means that the row is the better one when your hour markup is above
X. "Better below €X/h" means that it is the better one when your hour markup is below X. The best row shows no line,
and a row with no break-even value shows no line. A value from €0/h to €100/h is a link: a click opens the page with that hour markup, so the row is the better one after the click. The value is rounded up for "above" and down for "below". The other weights of the page stay. A value outside this range is text only.

### Seats left

A fare with 5 or fewer seats left shows the badge "N seats left" (or "1 seat left") on the trip page and on the pinned page. The count comes from the newest capture of the fare: an older capture does not change it. The sources that give the count are Eurostar, Flixbus and Trainline. A fare from another source, or a fare with more than 5 seats, shows no badge.

### Departure days

Above the table, the trip page shows a strip of the departure days. A trip with a date range shows each day of the range, up to the first 31 days. A day with no offer shows "no offers". Without a range, the strip shows each day that has an offer. The strip is hidden when it has fewer than two days.
Each day shows two costs: the best effective cost of the day (in the title "Best effective cost") and the cheapest price of the day (in the title "Cheapest price"). The costs use the active profile and the hidden offers do not count.
The strip shows all offers, also while one day is selected. Its costs do not change when you pick a day.
A day with no captured connection shows "from €49.99 (bahn.de day price)" when a bahn.de search with "Bestpreise anzeigen" gave a price for that day. The newest capture of a day wins. A day with connections shows its costs as before.
Click a day to show only the offers that depart on that local day. The filter is the query parameter `day`, in the form `YYYY-MM-DD`. The selected day is marked as current. Click "All days" to remove the filter.
A change of a slider keeps the selected day. The strip updates its costs with the new weights.

### Timeline of a trip

Above the table, the trip page shows a "Timeline" block. It shows the shown rows on a time axis, with one block for each departure day. The block is hidden when no row shows.
Each row of the table is one bar on the axis of its departure day. The bar starts at the departure and ends at the arrival, with the local times at its left and right. An arrival on a later calendar day shows " +1" (or " +2" and so on) after the time. A bar shows the badge "best value" when its row has that badge.
A bar has one part for each leg, in the colour of the mode of the leg: train, bus or flight. The parts show the order and the length of the legs.
A gap is a line between two parts. It is a transfer, and its title shows the minutes and the place of the transfer.
Click a bar to open its row: the page goes to the row and opens its "Legs and fares".
The timeline follows the table. A change of a slider, a filter or the day strip updates it, so it shows the same rows as the table.

### Price trend of a trip

The trip page shows a "Price trend" chart above the table. It shows the lowest price of the trip for each day, in EUR.
Each point is one day. Its title shows the date and the value, for example "2026-11-03: €90.00". The chart also shows the lowest and the highest value.
The value of a day follows this rule: for each fare, the app takes its newest price at the end of the day (UTC). It then takes the lowest EUR value of these prices. A day with no capture keeps the value of the day before. A price with no exchange rate does not count, and a hidden offer does not count.
The chart shows only when the trip has captures on 2 or more days.

### Earlier trips on the same route

The trip page shows an "Earlier trips on this route" card below the price trend. It lists the older trips with the same origin and destination. A split part of a trip does not count, and a trip on a later date does not count.
Each line shows the month of the older trip as a link to that trip, its cheapest seen price per traveler in EUR, and the price you paid for it per traveler, when you booked an offer of that trip. The cheapest price shows "-" when that trip has no price. The list shows at most 5 trips, the newest first.
The card shows only when the route has an older trip.

### When to book on this route

The trip page shows a "When to book on this route" card below the "Earlier trips on this route" card. It tells you how early the low prices came on this route.
Each row is a step of days before the departure: 0–7, 8–14, 15–30, 31–60, 61–90 and more than 90 days before. The row shows the lowest price per traveler in EUR that the app captured in that step.
Only captured prices count: the prices of this trip and of the older trips of the same route (the trips of "Earlier trips on this route"). A hidden offer, a price after the departure and a price with no currency rate do not count.
A step with no capture has no row. The card shows only when at least one step has a capture.

### What is new since your last view

A trip page counts as viewed when you open it in full. The app then remembers the time of the view. The next time you look, it shows what changed since then:
- The trips list shows "N new" next to a trip that has new offers (N is the number of new offers). A trip with no new offer shows no count.
- The trip page marks each row "new" whose offer was first captured after your last view.
- Each fare whose price changed since your last view shows the old and the new price, for example "€95.00 → €90.00". A rise and a fall both show.

A slider change on the trip page (the re-rank) does not count as a view: the marks stay until you open the trip page in full.
The first full view after a change shows the changes. A second full view shows none of them.

### Upcoming journeys

The "Upcoming" link in the app bar opens `/upcoming`. The page lists the booked journeys that have not arrived yet:
an offer that you marked as booked (see "Pin, hide, book and note an offer") shows here when the arrival of its
journey is now or later. A journey that has arrived no longer shows.

The journeys are in the order of their departure. Each journey shows:
- the title of its trip, with a link to the trip page,
- the date of its first leg, in the local time of the place of departure,
- each leg in the local time of its place: the carrier and the service number, the place of departure and of arrival,
  the departure and arrival times, and "+1 day" (or more) where the arrival is on a later day,
- the link "Add to calendar" at the right side, which downloads the `.ics` file of the journey (see "Add to calendar" below),
- "Paid" and the paid price of the journey, when the offer has a paid price (see "Pin, hide, book and note an offer").

The page also shows "Total paid: €..." above the list, the sum in EUR of the paid prices of the journeys. The EUR
values use the exchange rates of `/rates`. A paid price in a currency with no rate is not in the total. The page then
shows "(N price(s) in XXX has/have no rate)" after the total. With no paid price, the total line is not shown.

A journey with a conflict shows a warning under it, on this page and on the trip page of the journey, with the link
"Open the other trip". There are two kinds:
- "This journey overlaps another booked journey": the journey is in time at the same moment as another booked journey,
  of the same trip or of another trip.
- "This journey departs before the journey before it arrives": a booked journey of a trip departs before a booked
  journey of the trip before it arrives, for example a return journey that leaves before the outbound journey has arrived.
  The warning shows on the later journey only.

With no booked journey, the page shows the text "No booked journeys. Mark an offer as booked on its trip page."

The page also works with no network, after one online visit:
- The first online visit to `/upcoming` saves a copy of the page on the device.
- With no network, the page shows the saved copy with the line "Offline: saved at HH:MM", the time of the save.
- With no saved copy, the page shows "No saved journeys: open Upcoming once with a network."
- "Log out" deletes the saved copy from the device.
- "Add to calendar" needs a network. Offline, the link shows "Add to calendar: needs a network".

### Print the upcoming journeys

To print the page, open `/upcoming` and use the print command of your browser (Ctrl+P, or Cmd+P on a Mac).
To print one journey, click its "Print" icon: the page then shows only that journey.
In the print dialog you can print on paper, or choose "Save as PDF". A journey is kept on one page where the browser allows it.

The print has no app bar, no form and no buttons: only the journeys are printed. The print uses a white background and black text.

### Pin, hide, book and note an offer

Each row of the trip table has buttons at its left side:
- "Pin" keeps the offer at the top of the table, in every sort order. "Unpin" removes the pin.
- "Hide" removes the offer from the table and marks it "hidden". "Unhide" shows it again.
  The table does not show hidden offers, unless you tick "show hidden" above the table.
  An offer whose departure has passed is also left out, unless it is booked. Tick "show departed" above the table to see these offers, greyed, after the other rows. The best offer of the panel and of the journey does not use a departed offer either.
- "Mark as booked" adds a "booked" badge to the row. "Not booked" removes it.
  "Mark as booked" also stores the paid fare and the paid price: the main fare of the row (the fare with the lowest
  effective cost), its latest price and its currency, and the time of the booking. "Not booked" clears all four.
- A booked row shows "Paid €59.80", the paid price. When the latest price of the paid fare is in the same currency and
  is another price, the row adds ", now €89.00 (+€29.20)" (or "−" when the price is lower).
- To correct the paid fare or the paid price, open "Legs and fares" of the row. A booked row has
  the fields "Paid fare" (a select of the fares of the row) and "Paid price", and the button "Save paid price".
  The paid price is a number from 0 to 99999.99 with at most 2 decimals. A blank or a bad price shows an error (HTTP 422)
  and stores nothing.
- A new capture of the same journey keeps the paid price and the paid fare of the booked row.

The three buttons update the table in place: the page does not reload, and it keeps its scroll position.
Without JavaScript, each button sends the form and reloads the page.

To write a note on an offer, open "Legs and fares" in its row, change the text in the box and click "Save note".
A note has at most 2000 characters. The row shows the note under its route.

### Cancel a booked journey

A booked row of `/trips/{id}` has the form "Cancel booking" with the field "Refund" (the amount that you got back, in the paid currency). The refund is a number from 0 to the paid price with at most 2 decimals; a blank refund is 0. A bad refund shows an error (HTTP 422) and stores nothing.

After the cancel:

- The row is no longer booked. It leaves the Upcoming page, the calendar feed and the travel-day messages.
- The row shows "Booking cancelled: paid €89.00, refund €60.00", with the paid price and the refund. The paid fields stay.
- "Travel per year" counts the paid price less the refund for the year of the journey. It counts no journey, and no hours or CO₂, for it.

### Delay compensation of a booked train journey

A booked row of `/trips/{id}` whose journey has arrived has the form "Save delay" with the field "Delay at arrival (min)". Type the arrival delay as a whole number of minutes, from 0 to 1440. A blank field removes the delay. A bad value shows an error (HTTP 422) and stores nothing.

The row shows a claim when the journey has arrived and the delay is at least 60 minutes:

- A delay from 60 minutes gives 25 % of the paid price.
- A delay from 120 minutes gives 50 % of the paid price.

The claim shows its amount and its percentage, for example "Claim €45.00 (25 % for a delay of 75 min)". A journey with a bus or a flight leg, or with no paid price, shows no claim.

"Travel per year" lists the open claims under "Open claims", with the date, the route and the amount. Press "Claim paid" to mark a claim as paid. The row then shows "claim paid" and the claim leaves the list.

### Booking code of a booked journey

A booked row of `/trips/{id}` has the field "Booking code" with the button "Save code". Type the code of the booking, at most 40 characters. A blank field removes the code. A longer code shows an error (HTTP 422) and stores nothing. The row shows the code as "Booking code: <code>".

The Upcoming page shows "Booking code: <code>" in the box of each journey that has a code. The print layout of one journey (`/upcoming?only=<id>`) and its offline copy show it too. A journey with no code shows no booking code.

The shared page of a trip and the calendar feed do not show the booking code.

### Pinned offers

The "Pinned" link in the app bar opens `/pinned`. The link shows the number of pinned offers in brackets, for example "Pinned (3)".
The count is not shown when it is 0. The page lists the offers that you pinned (see "Pin, hide, book and note an offer")
when all of these are true: the offer is not hidden, and its trip is in planning (not booked and not archived).

The offers are in the order of their departure. Each offer shows:
- the title of its trip, with a link to the trip page,
- each leg: the carrier and the service number, the place of departure and of arrival, and the departure and arrival times,
- the latest price of its fare and the source of the fare. An offer with several fares shows the fare with the lowest latest price,
- "lowest €X, now €Y above" when the latest price is above the lowest price that the app has seen for this fare, or "at its lowest"
  when it is equal to it,
- "price dropped €X" when the price went down since the last view of the trip page (see "Price drops of a pinned offer"),
- the link "Open in trip", which opens the trip page at the offer.

With no pinned offer, the page shows the text "No pinned offers. Pin an offer on its trip page."

### Add to calendar

Only a booked row has the link "Add to calendar". Click it to download one `.ics` file of the itinerary of the row.
The file has one event per leg of the itinerary. Open the file with your calendar app to add the events.

The event times are in UTC, so your calendar app shows them in the time zone of your device.
The text of each event gives:
- the carrier and the service number, in the title of the event,
- the place of departure, in the location of the event,
- the local departure and arrival times, with their offsets from UTC, and the name of the trip, in the description.

### Subscribe in a calendar

The "Upcoming" page has a "Calendar" section. Click "Subscribe in a calendar" to make a link to a calendar feed of
all your booked journeys. The feed has one event for each leg of each booked journey. Its events are the same as in
the `.ics` file of "Add to calendar".

- The page shows the link once, with the button "Open in the calendar app" (it opens the `webcal://` link) and a field
  "Link to copy". Copy the link when it shows. The page shows it again only after you make a new link.
- Add the link to your calendar app as a new calendar subscription. Your app then reads the feed again, about every
  6 hours. Some apps read it less often.
- The feed holds the events of the booked journeys that arrive now or later, and of those that arrived up to 30 days
  ago. A booked journey
  shows in the feed after you book it, and it leaves the feed after you unbook it.
- The feed holds no note, no price and no API token. Anyone with the link can read the feed, with no login, so keep
  the link private.
- "Make a new link" makes a new link. The old link stops at once.
- "Revoke" stops the link at once: the old link then gives "not found". The page shows "No calendar link" again.

### Price drops of a pinned offer

A pinned offer whose price went down since the last view of its trip page shows a mark:
- The trips list shows "price dropped EUR X" after the best price of the trip. X is the largest drop of the trip.
- The trip page shows a box "Price drops" with the pinned offers that dropped.

Opening the trip page ends the mark: the next view shows no mark, unless the price drops again.
An unpinned offer or a hidden offer gives no mark.

#### Messages outside the app

The app can also send a message when a pinned fare drops. Choose the channel on the settings page (`/settings`, field
"Message on a price drop of a pinned fare"):

- `none`: no message (the default).
- `ntfy`: a plain-text message to the ntfy topic URL that you enter in "ntfy topic URL" (https only, for example
  `https://ntfy.sh/your-secret-topic`).
- `email`: an e-mail to the address in "E-mail address". It needs `SMTP_HOST` on the server; without it the settings
  page says so and does not save the channel.
- `webpush`: a push message to each browser that you turned on with "Turn on push on this device" (see below). It needs
  the VAPID variables on the server.

The settings page saves the channel only with what the channel needs: a missing address, topic URL or server setting
gives an error and changes nothing.

The messages settings page (`/settings/messages`) shows the last 50 messages that the app sent, under "Last messages".
Each row has the time, the title, the channel and the result. The result is "sent", or "failed" with a short reason
when the channel could not send the message.

Each message has the title "Price drop: " and the trip title, and one line for each dropped fare:
`fare name (source): EUR old price → EUR new price`. The message links to the trip page. One message goes to each trip
of an ingest. A failed send is logged and does not change the answer to the userscript.
A fare that comes to or below the target price of its trip (see "Target price of a trip") gives the title
"Target price: " and the trip title instead.

A booked journey with a "flexible" or "partly refundable" fare gives a message with the title "Booked fare cheaper: "
and the trip title when the price of that fare goes below the paid price. The message has one line:
`Booked <service>: now EUR new price, paid EUR paid price (−EUR difference), <tier> fare`. It uses the same channel as
the other price-drop messages, and it replaces the price-drop line of that fare. A non-refundable fare gives no
"Booked fare cheaper" message.

A "Search again" reminder asks you to search a trip again when its offers are old. It has the title "Search again: "
and the trip title, the search links of the trip, and the link of the trip page. It uses the channel that you chose
above. The reminder fetches nothing: the app only sends the message, and no travel site is contacted.

Two settings on the messages settings page (`/settings/messages`) control the reminders:

- "Reminder: age of the newest offers (days)": the number N. The default is `0`, which turns the reminders off.
- "Reminder: days before the departure": the number D. The default is `14`.

A trip gets a reminder when all of these are true: it is not archived; it has a pinned fare or a target price; it
departs today or within D days; its newest offers are older than N days, or it has none; and its last reminder is
older than N days, or it has none. So a trip gets at most one reminder in N days. The reminders are sent by the
service `backup` (see "Backups"), so that service must run. All times are UTC.

A travel-day message gives the legs of a booked journey before it departs. Its title is the day and the departure time,
for example "Tomorrow 09:15", and its text lists the legs with their local times. It uses the channel that you chose
above.

To turn it on, set "Travel-day message: hours before the departure" on the messages settings page
(`/settings/messages`) to the number of hours H, from 0 to 72. The default is `0`, which turns the messages off. With
H = 24, each booked journey gets its message at most 24 hours before it departs, once. The app checks the due messages
every 15 minutes, so a message comes at most 15 minutes after the set time. The messages are sent by the service
`backup` (see "Backups"), so that service must run. All times are UTC.

The app can send a message when the captures of a source fail. The checkbox "Send a message when the captures of a
source fail" on the messages settings page (`/settings/messages`) turns these messages on or off. It is on by default.
When the newest two or more captures of a source failed after its last good capture, the app sends a message with the
title "<source>: the last N captures failed" and a link to the failed captures of that source. The app sends it once for
each failure. When a good capture of the source comes, the app sends the message "<source> works again" with a link to
the captures of that source. The messages use the channel that you chose above; with `none`, no message is sent. The
app checks the captures when a userscript sends offers.

For Web Push, "Turn on push on this device" asks the browser for permission and subscribes it; "Remove push from this
device" removes that browser. The settings page shows how many devices have push on. On an iPhone or iPad, Web Push
works only in an app on the home screen: in Safari, tap Share, then "Add to Home Screen", and open the settings page
from there.

### Target price of a trip

A trip can have a target price in EUR. Set it in the trip form, in the field "Target price (EUR)". The field is optional,
and it must be between 0.01 and 100000. "Copy trip", the export and the import keep the target price.

When a trip has a target price, a fare is "at target" when its latest price in EUR is at or below the target:
- The trips list shows "at target" after the best price of the trip.
- The trip page shows a box "At your target price" with the fares that are at or below the target, the cheapest first.

A fare with no exchange rate is never "at target", and a hidden offer gives no mark.

The app can send a message when a fare comes to or below the target price. It uses the channel that you chose on the
settings page (see "Messages outside the app"; with `none`, no message is sent). The title is "Target price: " and the
trip title. A new message comes only when a capture brings a fare to or below the target. While the fare stays at or
below the target, no second message comes. After the price goes above the target and down again, a new message comes.

### Search status of each source

The trip page shows the list "Search status of each source", with one line for each source:
- The time and the offer count of the newest capture of the trip, for example "bahn.de: 2 h ago · 14 offers".
- "not searched yet" when no capture of the trip exists for the source.
- "last search failed" when the newest capture of the source failed. A link "Failed captures" opens the failed captures of the trip.
- The link "Search on <site>" when the source has a search link (see below).

A new source shows in the list by itself.

### Search links

The trip page shows a link "Search on <site>" for each source that has a search template and a value for the places of the trip. The link opens the site in a new tab.
- The link holds the from place, the to place and the date (`date_from`) of the trip.
- The from and to place of the trip must match a key of the source's `places` table in `app/data/search_links.toml` exactly, for example `Amsterdam`. A source gives no link when a place has no value for it, or when the trip has no date.
- The link only opens a page in your browser: the app sends no request to the travel site. After the search, the userscript captures the offers as usual.
- To add a source or change a value, edit `app/data/search_links.toml` (one table per source with `name`, `template`, `date_format` and a `places` table) and restart the app.

### Round trips

A round trip is two trips that are linked: an outbound trip and its return trip.
- The trip page of a one-way trip has the button "Make the return trip". It makes a linked trip with the origin and the destination swapped, and it opens the edit form of that trip. A return trip cannot have a return trip.
- The trips list shows each return trip directly under its outbound trip, with the text "Return of" and the name of the outbound trip. The line "Journey total" shows the sum of the EUR values of the two best offers. It shows no total when one direction has no offer or has only fares with no rate.
- The box "Journey" on the trip page of each direction has a link to the other direction. It shows the chosen offer of each direction (the booked offer, else the pinned offer, else the offer with the best effective cost) and the total effective cost. The box is a timeline with one row per part: the part's label and trip, its times and price, and its effective cost at the right. A warning shows as a chip. The total is at the bottom.
- The mark "The return departs before the outbound arrives" shows when the return departs before the outbound trip arrives.
- The trip page of each direction has the grid "Round trip: best sum per day", above the list of offers. The rows are the days of the outbound trip and the columns are the days of the return trip. Each cell shows the sum in EUR of the best effective cost of the outbound day and the best effective cost of the return day. A cell with no offer, or with a return day before the outbound day, shows "—". The grid shows up to 14 days of each direction.
- The cell with the lowest sum is the best cell. It has the class "best" and is marked "(best)" for screen readers. Only one cell is the best cell. No cell is the best cell when no cell has a sum.
- A click on a cell opens the trip page of the present direction, for the day of that direction in the cell. For the outbound trip, the day is the outbound day of the cell. For the return trip, the day is the return day of the cell. The other filters of the page stay.
- Deleting the outbound trip keeps the return trip. The link between the two trips goes away.

A journey can have three or more linked trips (multi-city). Each trip after the second one is a "next" trip.
- The trip page of a trip has the button "Add next trip". It makes a new trip at the end of the journey. The origin of the new trip is the destination of the last trip of the journey, and its destination is empty. Its title is the title of the first trip with "(part N)", where N is the number of the new trip. It opens the edit form of that trip. The button adds the trip to the end of the journey, also when you press it on a middle trip.
- The trips list shows the trips of a journey together, in sequence, under the first trip. The line "Journey price total" shows the sum of the EUR values of the best offer of each trip. It shows no total when one trip has no offer or has only fares with no rate.
- The box "Journey" on the trip page of each trip has a link to every other trip of the journey. It shows the chosen offer of each part (the booked offer, else the pinned offer, else the offer with the best effective cost), labelled "Part 1", "Part 2" and so on, and the total effective cost. The box is a timeline with one row per part: the part's label and trip, its times and price, and its effective cost at the right. A warning shows as a chip. The total is at the bottom. The mark "departs before the previous part arrives" shows at each part that departs before the previous part arrives.
- Deleting a middle trip removes it from the journey. The next trip links to the trip before the deleted trip, so the other trips stay in sequence.
- Archiving the journey (see "Archive a trip") moves all its trips to the archived list.

Each direction is a normal trip. The userscripts capture offers into it when you choose the trip in the dropdown of the panel.

### Other origins and destinations

A trip can have more than one origin or destination. On the form to make or change a trip, type the other places in
"Other origins" and "Other destinations", separated by commas (for example "Basel, Zürich"). The main place stays in
"Origin" and "Destination".
- The trips list and the trip page show the route with the other places, for example "Amsterdam → Zürich or Basel".
- A capture to any of these places goes to the trip, when its route matches the trip.
- The search links of the reminder messages and of the split tickets section cover each pair of an origin and a
  destination, with no pair twice. The trip page shows the search links of the main places only.
- The access and egress places of `/places` match the stations of each offer, as they do for any trip. An offer from an
  other origin or to an other destination uses the same rule.

### Split a trip via a place

To travel via a place, split the trip there. Use the form "Split via" on the edit page of a trip, and type the place (for example "Köln").
- The button "Split trip" makes two trips: from the origin of the trip to the place, and from the place to the destination. Their titles are "Origin → Place" and "Place → Destination". They keep the dates, the travelers and the score profile of the trip. A trip with no place shows "Split via: enter a place."
- A split trip has no "Split via" form: a split trip cannot have split trips. The page of a split trip shows "Part of" and a link to its trip.
- The trips list shows each split trip under its trip, with the text "split via" and the place.
- The trip page has one section "Split tickets via <place>" for each place. The section lists the two split trips, with "No offers yet." for a part with no offers. It shows the best pairs of offers, cheapest first: a connection of the first part, a wait at the place and a connection of the second part. Each pair shows its times, its transfer (the wait), its sum of effective costs and the difference to the best direct offer of the trip ("less than" or "more than").
- A pair needs a wait of at least the short-transfer minutes of the score profile (10 minutes by default) and at most 6 hours. A pair with a shorter wait does not show.
- The pairs follow the score profile of the trip, so a change of the profile changes their order.
- The edit page of a trip shows "Transfer places of your offers": the places where your captured offers change, most frequent first, with at most 5 places. Each place has a button "Split via <place>" that makes the split trips for that place. The button shows the number of offers with that place.
- The trip page shows the same places in one line, "Transfer places of these offers", with a link "Split the trip" to the edit page.

### Copy a trip

- The edit form `/trips/{id}/edit` of an existing trip has the button "Copy trip". It makes a new trip with the origin, destination, travelers, profile and note of the trip. Its title is the title of the trip with "(copy)". The new trip has no dates, no link to the trip and no offers. It opens its edit form. The original trip does not change.
- The edit form of a trip of a journey with two or more trips has the button "Copy journey". It makes a copy of each trip of the journey, in the same order, and links each copy to the copy before it. The copies show in the trips list as one journey, with no offers. It opens the edit form of the first copy. The original journey does not change.

### Merge two trips

To merge two trips, open the edit form of the trip that goes away, choose the target trip under "Merge into another trip" and click "Merge…". The offers, prices, captures, day prices and marks (pinned, booked, hidden and note) of the trip move to the target trip, and the merged trip is deleted. A trip that is linked to another trip (a return or a split) cannot be the trip that goes away.

### Duplicate trip warning

When another trip in planning has the same route and dates, the trip page shows the box "A trip on this route and date already exists:" above the route history. The box lists each such trip with a link to its page and a link "Merge" to `/trips/{id}/merge`, which merges the trip into the other one (see "Merge two trips"). A trip with no duplicate shows no box. The shared page does not show the box.

### Delete a trip

- The edit form `/trips/{id}/edit` has the link "Delete trip". It opens the confirm page. The page shows the number of itineraries and captures of the trip.
- Press "Delete" to delete the trip. Press "Cancel" to go back to the edit form. The delete cannot be undone.
- The delete removes the trip with its offers (itineraries), their fares and price history, and its captures. The app then opens the trips list.
- After the delete, the trip is not in the trips list, not in `GET /api/trips` and not in the trip dropdown of the userscript panel. Each page of the trip gives 404.
- A linked return trip stays, with no link (see "Round trips" above).

### Archive a trip

- A trip has the status `planning` (the default), `booked` or `archived`. Set it in the edit form `/trips/{id}/edit` (field "Status").
- The trips list `/` does not show the archived trips. When there are archived trips, it has the link "Archived trips (N)". It opens `/?archived=1` with the title "Archived trips" and the link "Trips" back.
- The field "Find trips" on the trips list searches the title, origin, destination and note of a trip. It ignores upper and lower case and accents. A journey shows whole. The archived trips that match show below the other results, under "In the archive (N)".
- A return trip shows in the list of its outbound trip: the status of the outbound trip decides for both (see "Round trips" above).
- The trip dropdown of the userscript panel shows only the trips with the status `planning`.
- An archived trip keeps its offers and captures. Set the status again to bring it back to the trips list.

### Tags of a trip

- The trip form (the form to create a trip and the edit form `/trips/{id}/edit`) has the field "Tags". Type the tags separated by commas, for example `work, summer 2027`.
- A trip has at most 5 tags. A tag has at most 20 characters. A form with more tags, or with a longer tag, gives an error and saves nothing.
- The trips list `/` shows the tags of each trip under its title. A click on a tag filters the list: `/?tag=work` shows only the trips with that tag. The filter ignores upper and lower case and accents. The link "Show all trips" removes the filter.
- The export and the import keep the tags. The JSON export (see "Export a trip") has the tags of the trip. The import (see "Import a trip") sets the tags of a new trip. An import into a trip that exists keeps the tags of that trip. The copy of a trip (see "Copy a trip") keeps its tags too.

### Export a trip

- The trip page `/trips/{id}` has the links "Export CSV" and "Export JSON". They are in the "More" menu of the page.
- Both links need the login. They do not need an API token.
- The JSON file (`/trips/{id}/export.json`) has the trip, its itineraries, the legs of each itinerary, the fares of each itinerary and the price history of each fare. The times are in UTC with the original offset. The money is text, not a number.
- The CSV file (`/trips/{id}/export.csv`) has one row per fare. The columns are the route, the departure, the arrival, the duration, the transfers, the modes, the carriers, the service numbers, the source, the fare, the column `travel_class` (`first`, `standard` or empty), the price, the currency, the capture time, the pinned, hidden and booked flags, the note and the booking link. The file starts with a UTF-8 byte order mark, so that a spreadsheet opens the accents correctly.
- A cell that a spreadsheet could run as a formula starts with a quote `'`. Such a cell starts with `=`, `+`, `-`, `@`, a tab or a carriage return.
- The paid fields of each itinerary in the JSON export are `booked_price` (the paid price as text, or null), `booked_currency`,
  `booked_at` and `booked_fare` (the position of the paid fare in the `fares` of the itinerary, or null).
- The CSV column `paid` is the paid price on the row of the paid fare. The other rows have an empty cell.
- The raw captures are not in the export.

### Import a trip

- The trips list `/` has the button "Import trip". It opens the import page `/trips/import`. The import page needs the login.
- The input is a JSON export file of "Export a trip" above. The app reads only the format version 1. Another version, or a file that is not JSON, gives an error and nothing is added.
- The page has the field "Import into". It has two choices: "A new trip" (the default) or one trip of the list. The list shows only the trips with the status `planning`.
- When you select a file, the page selects the trip with the same title, origin, destination and dates as the file. A second import of the same file then goes into the same trip.
- The import adds the itineraries, the fares and the price history that the trip does not have yet. An itinerary is the same when its legs are the same. A fare is the same when its source and fare name are the same. A price is the same when its capture time, price and currency are the same.
- The import keeps the paid fields of "Export a trip" above. An export from an older version has no paid fields: its
  itineraries import with no paid price.
- A second import of the same file adds no row. The counts show as "unchanged" instead.
- After the import, the app opens the trip. A message at the top shows the counts: the itineraries, the fares and the prices that were added, and the number of rows that were unchanged.
- The file can be at most 5,000,000 bytes, the same limit as the API body.
- If one itinerary in the file is not valid, the whole import stops and no row is added.
- Example: to move a trip from the preview server or from an old install to your own instance, open the trip on the old install and choose "Export JSON". On your instance, open "Import trip", select the file, keep "A new trip" and choose "Import". Open the trip to check the counts. A later import of the same file into the same trip adds nothing.

### Export and import the settings

- The settings page `/settings` has the button "Export the settings". It downloads one JSON file, `travel-aggregator-settings-<date>.json`. The import page `/settings/import` opens with the button "Import settings".
- The file has the score profiles with their weights, the places with their access and egress times and costs, the exchange rates, the booking fees of the sources, and the settings of the retention period, the reminders and the source-failure messages.
- The file has no secret, no address and no state. The channel of the price-drop messages (its ntfy topic URL and e-mail address), the push subscriptions and the API tokens are not in the file. Set them again on your instance (`/settings/messages`, `/settings`, `/tokens`).
- The file must be version 1. A file with an unknown setting, a wrong value or a missing field gives an error, and no row changes.
- The import rule: the file wins. Each profile, place, rate, fee and setting of the file replaces the value of the same name on your instance. The rows that are not in the file stay.
- At most one profile of the file can be the default.
- To move your instance to an empty database: export the settings and the trips, install the new instance, import the settings first, then import each trip under "Import a trip".

### Version of the app

- The settings page `/settings` has the card "Version". It shows the commit that runs, with a link to that commit on GitHub (no link when the app runs without an image), and the time when the image was built (UTC).
- The card also shows the database revision. When the database is not at the newest migration, the card shows the mark "migrations pending" and the newest revision (head).
- The same commit and build time are in `GET /api/health`: the keys `commit` and `built`. Use it to check the version of a server without a login.

### Share a trip read-only

A trip has one read-only link for a travel partner. On `/trips/{id}`, click "Share". The page shows the new link once:
copy it then. Each person with the link sees the offers of the trip, with no login.
The trips list shows the mark "shared" after the trips that have a link.

The shared page `/s/<token>` lists the offers that are not hidden, best effective cost first. Each offer shows the route,
the times, the duration, the transfers, the fare and price, the effective cost with its breakdown, and its legs.
The page uses the profile of the trip. The sliders and filters of the trip page do not apply.
The shared page does not show the notes of the trip, the booking links, the price captures or history, the hidden offers, or any
control such as pin, book or delete.

The travel partner can mark an offer with "Suits me". A marked offer shows the mark "Suits you" on the shared page. The
partner can add a note of up to 200 characters with the mark; the note is shown as text on the shared page, and the partner can
change it with "Save note" or remove the mark and its note with "Remove". The trip page shows the marks to the owner.
"Revoke link" deletes the marks of the trip.

To stop the link, click "Revoke link" on the trip page. The link then returns "not found" (404). "Share" shows again
after "Revoke link", and it makes a new link: the old link stays stopped. Each address that sends too many wrong
links gets HTTP 429 with a `Retry-After` header for a while.

### Compare offers side by side

To compare 2 to 4 offers of a trip:
1. On `/trips/{id}`, tick the box "Compare" of each row. Tick 2 to 4 rows.
2. When one or more rows are ticked, a bar shows under the table with the text "Compare N selected", where N is the
   count of ticked rows. Click "Compare" in the bar. The page `/trips/{id}/compare` opens.

The amounts on the compare page and on the price history page show in the same money format as the trip page, for
example `€78.00`.

The page shows one column for each ticked offer. The lines are the route, the departure and arrival times, the duration,
the transfers, the modes, the carriers, the fare, the price and the effective cost with its breakdown.
The best value of each line has the mark "best": the lowest price, duration, transfers and effective cost.
A tie marks every column with the lowest value.
The last line is "Break-even (yours: €X/h)". Each column that is not the best shows the hour value at which it and the
best column have the same effective cost, for example "Better above €12.50/h". "Better above €X/h" means that the column
is the better one when your hour markup is above X. "Better below €X/h" means that it is the better one when your hour
markup is below X. The column with the lowest effective cost shows "Best now". A column with no break-even value shows
"—". A value from €0/h to €100/h is a link: a click opens the page with that hour markup, so the column is the better
one after the click. The value is rounded up for "above" and down for "below". The other weights of the page stay.
A value outside this range is text only.
The page uses the same weights as the trip page: the two sliders, and the profile that you chose there.
Click "Back to the trip" to return to the trip page with the same weights.
If you tick fewer than 2 or more than 4 offers, the page shows an error and asks you to select again.


The trip page has a link "Add an offer by hand" above the offer table. It opens the form `/trips/{id}/offers/new`.
The form has a price (required), a currency (EUR by default), an optional fare name, a field "Class" (`Not set`, `1st class` or `2nd class`; `Not set` stores no class) and the UTC offset of the times.
Each leg has a mode, a from and to place, a departure and an arrival. The form has up to four legs. A leg with no field filled in is left out.
The app saves the offer with the source `manual`. Save returns you to the trip page, where the offer is ranked with the others.

### Correct a manual offer

A manual fare on `/trips/{id}` has the links "Change price" and "Delete" under its price. "Change price" opens a form with the price and the currency; "Save price" adds a point to the price history of the fare. "Delete" opens a page with the button "Delete offer", and removes the manual fare. The offer goes too when it has no other fare. A captured fare has no such links: use "Hide" to remove it from the table (see "Pin, hide, book and note an offer").

### Travel per year

The page "Travel per year" (`/upcoming/years`) shows the booked journeys of each year, newest year first. The link
"Travel per year" is on the Upcoming page. The journeys that you marked as booked are counted. A cancelled booking is no journey: it adds its paid price less its refund (see "Cancel a booked journey").

For each year the page shows:

- the number of booked journeys and the sum of their paid prices in EUR;
- the hours of travel, rounded to the nearest hour;
- one line for each mode (train, bus, flight, and so on) with its journeys, its paid sum and its hours.

The rules:

- The year is the year of the local departure of the first leg of the journey.
- A journey with more than one mode counts for the mode with the most minutes of legs. A tie goes to the mode of the first such leg.
- A price in another currency is changed to EUR with the rate that the app has. A price with no rate is not in the sum. The page
  says how many prices of each currency have no rate.
- A journey with no paid price counts as a journey, but adds nothing to the sum.
- The CO₂ is an estimate per traveler: the hours of each leg times the kg per hour of its mode, with the kg per hour of the default profile. The page shows "about N kg CO₂" for each year and each mode, and names the profile.

Each year has the link "Export CSV". It downloads the file `travel-<year>.csv` (`/upcoming/years/<year>/export.csv`)
with one row for each booked or cancelled journey of the year, in the order of departure. The year of a journey has the
rule above. The columns:

- `date`: the local date of departure of the first leg;
- `route`: the place of departure of the first leg and the place of arrival of the last leg;
- `modes` and `carriers`: the modes and the carriers of the legs;
- `status`: `booked`, or `cancelled` for a cancelled booking;
- `paid` and `currency`: the paid price and its currency (EUR when the booking has no currency);
- `paid_eur`: the EUR value of the paid price;
- `refund` and `refund_eur`: the refund of a cancelled booking and its EUR value (empty for a booked journey);
- `claim_paid`: the amount of the delay claim, when you pressed "Claim paid" (see "Delay compensation of a booked train journey").

The sum of `paid_eur` less the sum of `refund_eur` is the paid sum of the year on the page. A price with no rate to EUR
has empty EUR cells, and is not in that sum. A journey with no paid price has an empty `paid` cell. The file starts with a
UTF-8 byte order mark, so that a spreadsheet opens the accents correctly.

## Userscript panel

Each userscript shows a small panel at the bottom right of the travel site. The panel shows `Captured N offers → sent ✓`
when the offers reached your server, or an error message.

- **Trip.** The dropdown chooses the trip that receives the offers. `+ new trip` makes a trip with the title that you
  type. The app remembers the chosen trip.
- **Auto-select trip.** This check box is on by default. With it on, the app chooses the trip of each capture. It uses
  the selected trip when the offers match it. Else it uses the one trip in planning that matches the offers (when more
  match, the one with the shortest date range, then the newest). Else it keeps the selected trip, and the trip warning
  shows (see "Trip warning of a capture"). The dropdown then shows the trip that got the offers. When no trip matches,
  `+ new trip` is filled from the offers: the title is the route of the offers, and the places and the first departure
  day are set.
- **Best offer.** After a sent capture, the panel adds the best offer of the trip, for example
  `Captured 1 offers → sent ✓ · Best of trip: €182 (new)`. The best offer is the one with the lowest effective cost by
  the profile of the trip. `(new)` means that this capture made it better. Whole euros show without decimals, other
  amounts with two decimals. A warning keeps its text and style, with the best offer after it.
- **Auto-send.** This check box is on by default. With it on, the offers are sent at once. With it off, the offers wait
  in the queue until you press Send.
- **Settings.** Set the server URL and the API token once, in the Tampermonkey menu (`Set server URL`, `Set API token`).
  Make the token on the `/tokens` page.
- **Not sent.** When a send fails, the offers stay in the queue. With auto-send on, the userscript sends them again
  later.
- **Resend.** The userscript gives each capture a key of its own. When the answer of the server gets lost and the
  userscript sends the capture again, the server stores the capture once. The resend gives no second capture and no
  second price row. Userscripts of an older version send no key, and they work as before.
- **Server busy.** When the app answers `429` (too many requests, or too many bad tokens from your address), the panel
  shows `Server busy: kept in the queue`. The offers stay in the queue and the userscript sends them again later.
  See "API" for the limits.
- **Queue.** The queue keeps up to 20 captures. The panel shows `N captures wait (oldest M min)`. A 21st capture drops
  the oldest one, and the next panel status starts with `1 old capture dropped.`
- **Queue commands.** The Tampermonkey menu has `Send now`, which sends the queue at once, oldest first. It also has
  `Discard the queue`, which empties the queue and shows `Discarded N captures`. It sends no request to the server.
- **No offers seen.** On a results page of bahn.de, Eurostar or SNCF Connect, the panel shows `No offers seen on this
  page` when no search response that the userscript accepts came within 30 seconds. The site may have changed the
  address of its search response. See "No offers seen on a results page".

### bahn.de userscript

The bahn.de userscript captures the search results of bahn.de: the connections, their times and their fares.
It reads only the responses that the bahn.de page itself gets. It sends no request to bahn.de.
With "Bestpreise anzeigen" on, the userscript also sends the day prices (`/web/api/angebote/tagesbestpreis`). They are no offers and do not show in the table.

To install it, add the file `userscripts/bahn.user.js` of this repository to Tampermonkey as a new script.
Then set the server URL and the API token in the Tampermonkey menu. On bahn.de, search for a connection. The panel
shows the number of captured offers.

The parser reads the fare name with its class and its BahnCard discount. The class of each fare is stored as the travel class (see "API"). It gives each station its own timezone. A
connection with no price goes to the errors of the capture and is not stored as an offer.

### NS International userscript

The NS International userscript captures the search results of nsinternational.com: the connections, their times and
their fares. It reads only the responses that the nsinternational.com page itself gets. It sends no request to
nsinternational.com.

To install it, add the file `userscripts/ns.user.js` of this repository to Tampermonkey as a new script.
Then set the server URL and the API token in the Tampermonkey menu. On nsinternational.com, search for a connection.
The panel shows the number of captured offers.

The parser reads the fare name with its flexibility level. It gives each station its own timezone. A connection that
the parser cannot read goes to the errors of the capture and is not stored as an offer.

### Kiwi.com userscript

The Kiwi.com userscript captures the flight offers of kiwi.com: the flights, their times and the price of each fare.
It reads only the responses that the kiwi.com page itself gets. It sends no request to kiwi.com or skypicker.com.

To install it, add the file `userscripts/kiwi.user.js` of this repository to Tampermonkey as a new script.
Then set the server URL and the API token in the Tampermonkey menu. On kiwi.com, search for a flight.
The panel shows the number of captured offers.

The parser makes one offer per fare. It reads the time zone of each airport from the times of the response. A
segment with a guarantee starts a new ticket, so the flights of that offer count as a self-transfer. A flight that the
parser cannot read goes to the errors of the capture and is not stored as an offer.

### Flixbus userscript

The Flixbus userscript captures the search results of flixbus.com: the connections, their times and their prices.
It reads only the responses that the Flixbus page itself gets. It sends no request to flixbus.com.

To install it, add the file `userscripts/flixbus.user.js` of this repository to Tampermonkey as a new script.
Then set the server URL and the API token in the Tampermonkey menu. On flixbus.com, search for a connection.
The panel shows the number of captured offers.

The parser reads the currency from the search address of the page. It takes the fare name from the transfer type of
each connection. A connection that the parser cannot read goes to the errors of the capture and is not stored as an
offer.

### SNCF Connect userscript

The SNCF Connect userscript captures the search results of www.sncf-connect.com: the trains, their times and their
fares. It reads only the responses that the SNCF Connect page itself gets. It sends no request to sncf-connect.com.

To install it, add the file `userscripts/sncf.user.js` of this repository to Tampermonkey as a new script.
Then set the server URL and the API token in the Tampermonkey menu. On www.sncf-connect.com, search for a train.
The panel shows the number of captured offers.

The trains that show are TGV INOUI, OUIGO and TER, with the first-class and second-class fares. The trip page has no
SNCF Connect search link: the name of the site shows only in the search status.

The parser makes one offer per fare. It reads the times of France and adds the offset of Europe/Paris for the date of
each leg. A train that the parser cannot read goes to the errors of the capture and is not stored as an offer.

### Trainline userscript

The Trainline userscript captures the search results of thetrainline.com: the journeys, their times and their prices.
It reads only the responses that the Trainline page itself gets. It sends no request to thetrainline.com.

To install it, add the file `userscripts/trainline.user.js` of this repository to Tampermonkey as a new script.
Then set the server URL and the API token in the Tampermonkey menu. On thetrainline.com, search for a journey.
The panel shows the number of captured offers.

The date of birth of each passenger is not sent to your server. A train that bahn.de also sells is one row on the
trip page: its offers from bahn.de and from Trainline count as the same itinerary.

### Eurostar userscript

The Eurostar userscript captures the search results of eurostar.com: the trains, their times and the prices of the
Standard, Plus and Premier fares.
It reads only the responses that the Eurostar page itself gets. It sends no request to eurostar.com.

To install it, add the file `userscripts/eurostar.user.js` of this repository to Tampermonkey as a new script.
Then set the server URL and the API token in the Tampermonkey menu. On eurostar.com, search for a journey.
The panel shows the number of captured offers.

The search status of a trip shows a search link to eurostar.com. Use it to open the same search on the site.

### ÖBB userscript

The ÖBB userscript captures the search results of shop.oebbtickets.at: the connections with their times and the
prices of the results list. When you open the offers of a Nightjet, it also captures its Seat, Couchette and Sleeper
fares.
It reads only the responses that the ÖBB page itself gets. It sends no request to oebbtickets.at.

To install it, add the file `userscripts/oebb.user.js` of this repository to Tampermonkey as a new script.
Then set the server URL and the API token in the Tampermonkey menu. On shop.oebbtickets.at, search for a journey and
wait until the prices show in the list. The panel shows the number of captured offers.

The trip page has no ÖBB search link yet. Open the search on the ÖBB site yourself.

### Parse result of a capture

The column "Captured" shows the age of each capture, for example "2 h ago". Point at the age to see the full UTC time.

Each capture on the captures pages has these columns:

- "Offers": the offers that the parser read.
- "Rejected": the offers that the parser rejected.
- "Result": "ok", or "failed". Open "failed" to see the reason: the reason when the parser cannot read the raw data,
  and "offer N: reason" for each rejected offer.
- "Check the price": the number of fares of the capture that show the chip "check the price" (see "Compare offers in the trip table"). The number has the warning style when it is more than 0, and "-" when the capture has no offer.

A capture from the time before this feature shows "-" in these columns. The reasons do not show the input values.

A capture is failed when the parser cannot read it or rejects one or more offers. Open `/captures` or
`/trips/{id}/captures` and press "Only failed captures" to see only the failed captures. Press "Show all captures" to
see all captures again.

### Reparse a capture

Open `/trips/{id}/captures` and press "reparse capture" on a capture. The app runs the current parser on the stored raw
data of that capture and shows how many offers it read. Use this after the parser of a source is fixed. The button
does not send a request to the travel site. A capture with no raw data, or a source with no parser, cannot be reparsed.

To reparse all failed captures of a source in one step, open `/captures` and press "Only failed captures" (`/captures?failed=1`).
The page has one button "Reparse all failed captures of <source>" for each source with failed captures that have raw data.
The failed captures page of one trip (`/trips/{id}/captures?failed=1`) has the same buttons. The button runs the current
parser on each failed capture of that source with raw data, of all trips, and shows: "Reparsed N captures of <source> with
<version>: X now parse, Y still fail; C created, U updated." One click reparses at most 500 captures. When more wait, the
text says "More than 500 captures wait: click again." A source with no parser shows "The source <source> has no parser."
The button does not send a request to the travel site.

A reparse replaces the stored parse result with the new one. Reload the page to see it.

### Raw payload of a capture

The captures pages have a "Raw" link for each capture with raw data. The link opens `/captures/{id}/raw`: the source, the
capture id and the raw payload as text. A capture with no raw data shows "No raw payload" instead of the link.
A long payload shows only its start, with the note "The payload is N KB; download it to see all of it."
The button "Download JSON" on that page downloads the whole raw payload as a JSON file named `<source>-<id>.json`.

The link "Download for a bug report" on that page (`/captures/{id}/report.json`) downloads the same payload as a file named `<source>-<id>-report.json` with the
personal values replaced by `"REDACTED"`: names, e-mail addresses, phone numbers, dates of birth, card and booking numbers,
and the personal keys that the parser of the source names. The prices, the connections and the response stay as they are,
so a parser fix can read the file. Check the file before you attach it to an issue: the app cannot find every personal value.

### Best offers by source

The card "Best offers by source" on `/captures` shows, for each source, two numbers, for example "bahn.de: best in 3 of 5 trips (last 12 months)":

- The second number (5) is the trips with a capture of that source in the last 12 months.
- The first number (3) is the trips whose best offer has its main fare from that source. The best offer is the one with the lowest effective cost by your default profile (not the profile of the trip), at the newest capture of the trip.

Hidden offers do not count, and an offer that had departed at the newest capture does not count. The card shows only on the page of all captures. It does not show with the filters "Only failed captures" or `?source=`, and it does not show when there are no captures. The card uses the display name of the source from `search_links.toml`.

### Upload a payload file

Use the form "Upload a payload" on `/trips/{id}/captures` to store a saved JSON file as a capture of the trip. The app
parses it and stores its offers, as if a userscript had sent it. Use it for a payload that you saved from a capture
with "Download JSON".

- Choose the source in the select, or choose "From the file name". With "From the file name", the source is the part of
  the file name before `-<number>.json`: `bahn.de-1234.json` gives the source `bahn.de`.
- The source must have a parser. A file name with no source, or with a source that has no parser, gives the message
  "Choose the source: the file name does not name one". Nothing is stored.
- The file must be JSON. Otherwise the page shows "The file is not JSON.", or "Select a payload file." when no file is
  chosen, or "The file is larger than N bytes." when it is too large. Nothing is stored.
- The upload does not send a request to the travel site.

### Upload a HAR file

You can also upload a HAR file of a search on `/trips/{id}/captures`. The same form takes it: choose the HAR file, or a
JSON file with a `log.entries` list. Use it when no userscript captured the search, for example when you saved the
network log of a travel site yourself.

1. In the browser, open the developer tools on the search page, and open the Network tab.
2. Run the search, and wait until the results show.
3. Save the network log as a HAR file. In Chrome, choose "Save all as HAR with content".

The app reads each search entry of a supported source and stores it as a capture of the trip. The page then shows the
line "N captures from the HAR file", and the captures list shows each one with its offer count. Other entries are skipped.

- A HAR file with no search entry of a supported source gives the message "The HAR file has no search entry of a
  supported source." Nothing is stored.
- A file that is not JSON, or that has no `log.entries` list, gives "The HAR file cannot be read". Nothing is stored.
- A HAR file larger than 30 MB gives "The HAR file is larger than 30000000 bytes." Nothing is stored.
- The app reads only the address, the method, and the request and response bodies of each entry. It never keeps the
  headers or the cookies of the file.

### No offers seen on a results page

When the panel shows `No offers seen on this page`, the userscript loaded a results page and no search response
that it accepts came. The app then stores the page: the source, the address of the page without the host, the time,
and the version of the userscript. The app stores no offers for it.

- The page `/captures` shows the line `<source>: N results page(s) with no offers seen (HH:MM)` above the list of
  captures, with the time of the newest such page. The line shows only when such a page exists.
- The panel line is a warning only. It sends no request to the travel site and shows no browser dialog.
- What to do: first update the userscript (`/tokens` has the install link). If the line stays, upload the payload of
  the search with "Upload a payload file" or the HAR file of the search with "Upload a HAR file" (see above), so the
  offers reach the app.

### Status of the sources

The page `/captures` shows the status of each source above the list of captures, in a table with the columns "Source",
"Last good capture", "Parser" and "Failed after it":

- "Last good capture" is the time of the newest capture that the parser read with no rejected offer. "never" means that
  no capture of the source is good yet.
- "Parser" is the version of the parser that read the newest good capture. When the newest capture of the source came
  from an older userscript (version A) and the app serves a newer version B, the cell also shows "old userscript A:
  update to B". The warning is a link to `/tokens`: open the install link of the userscript there. Tampermonkey
  checks for a new version about once a day, so the warning can show for some hours after an update. A capture with
  no userscript version (an upload, a manual offer) shows no warning.
- "Failed after it" is the number of failed captures of the source after the last good capture. A failed capture is
  a capture that the parser could not read, or that it read with at least one rejected offer.

The table shows only on the page of all captures, with no filter. The filter by source (`/captures?source=<source>`)
and the page "Only failed captures" (`/captures?failed=1`) do not show it.

To see the captures of one source, add the source to the address (`/captures?source=<source>`). The page then shows
"Source: <source>" and the link "All sources". The filter combines with "Only failed captures": `/captures?failed=1&source=<source>`
shows only the failed captures of that source.

The trips list shows a warning for each source with two or more failed captures after its last good capture. The warning
reads "<source>: the last N captures failed", where N is the number of those failed captures. The warning is a link to
the failed captures of that source (`/captures?failed=1&source=<source>`). The warning goes away when a good capture of
that source arrives, or when a reparse (see "Reparse a capture") makes the newest captures good.

### Trip warning of a capture

The app checks the offers of a capture against the trip. When no offer matches the trip, the app shows a warning with
the reason:

- `places`: no offer goes from the origin of the trip to its destination. A station code (for example `LIS`) matches
  the place, and so does the local name of a place (for example `München` for `Munich`). Words of fewer than 3 letters
  do not count.
- `date`: the offers of those places depart on a date outside the dates of the trip.

One matching offer is enough for no warning. A part of the trip that is empty is not compared.

The warning is a hint only: the app stores the offers in any case. The warning shows in two places:

- The userscript panel: "Captured N offers → sent ✓, but these offers do not match the trip", in the warning style.
- The captures pages (`/captures` and `/trips/{id}/captures`): the column of the capture shows "These offers do not
  match the trip".

The response of `POST /api/ingest` has the field `warning`: `"These offers do not match the trip (places)"` or
`"... (date)"`, or `null` when there is no warning.

A reparse (see "Reparse a capture") computes the warning again, for example after you change the places of the trip.

With "Auto-select trip" on in the userscript panel, the app first looks for a trip that matches the offers (see "Auto-select trip" under "Userscript panel").

### Move to trip

Use this when a capture went to the wrong trip. Open `/captures` or `/trips/{id}/captures`. The column of each capture
with raw data has a list of the other trips (not archived) and the button "Move to trip". Select the correct trip and
press the button. The page shows the result, for example "Moved to <trip>: N created, N updated, N unchanged, N rejected."

- The offers of the capture go to the selected trip, and they leave the old trip.
- An offer that another capture of the old trip also has stays in the old trip.
- An itinerary that leaves the old trip gives its pin, booked mark, hidden mark and note to the same journey in the
  selected trip.
- A capture with no raw data cannot move. A source with no parser cannot move either.
- A move does not send a price-drop message. The move is not a new capture.

The move parses the stored raw data again. It does not send a request to the travel site. When the parser cannot read
the raw data, nothing moves, and the page shows the reason.

### Capture retention

A capture is the raw data that the userscript sent to the server. The app keeps each capture for a number of days.
Open `/settings` to set the retention period. The default is 90 days. Enter `0` to keep all captures. The maximum is
3650 days. Each ingest deletes the captures that are older than the period. The offers and their price history stay.

The card "Storage" on `/settings` shows the size of the database and of the raw captures. It shows the number of captures
and the raw size of each source. It also shows the captures that the next cleanup removes at the current period.

A deleted capture cannot be reparsed (see above). Set a longer period before you need to reparse an old capture.

## Ranking

The trip page `/trips/{id}` ranks the offers by effective cost, lowest first:

```
effective cost = price + hours × hour markup + transfers × transfer markup + door-to-door parts
```

The door-to-door parts are described below.

Each row shows the breakdown of its cost, for example `€90 price + €62 time + €30 transfers = €182`. A part that is
0 is not shown. Two sliders above the list set the hour markup (default €15) and the transfer markup (default €10),
from €0 to €100. When you move a slider, the list ranks again at once. While the new list loads, the table is dimmed.
The values are not stored: a link such as `/trips/1?hour_markup=20&transfer_markup=5` opens the page with them.

### Score profiles

A score profile stores the weights of the sliders under a name.

- To save a profile, open a trip page, enter a name under "Advanced" and press "Save as profile". The profile stores the
  weights that the page shows at that moment.
- One profile is the default. The default profile gives the weights of a trip page that has no other profile.
  Set the default on `/profiles`.
- A trip can have its own profile. Choose it in the trip edit form `/trips/{id}/edit`.
- The switcher "Profile" on the trip page (`/trips/{id}?profile=<id>`) selects a profile for that page.
- The trip page shows "Best by profile" when you have two or more profiles. It lists the best offer of each profile
  with its time and its total cost. The name of each profile is a link that selects that profile, and the active
  profile is marked "(active)". With one profile, the section does not show.

When the page ranks the offers, a value comes from the first source that has it, in this order:

1. a weight in the URL (a slider or a link with `hour_markup` or `transfer_markup`)
2. the profile of the switcher (`profile=<id>`)
3. the profile of the trip
4. the default profile
5. the defaults of the sliders (€15 for the hour markup, €10 for the transfer markup)

The profiles are listed, changed and deleted on `/profiles`.

To make a profile with no trip, open `/profiles/new`. Enter a name and the weights, and press "Save". To change the
weights of a profile later, press "Edit" for the profile on `/profiles`. This opens `/profiles/{id}`: change the values
and press "Save".

#### Hour value of your bookings

The edit page of a profile (`/profiles/{id}`) suggests an hour value from your bookings. The suggestion uses the
weights of that profile.

- A booking counts when you booked a journey or cancelled it, and the journey has a booking time. The other offers
  of the same trip count when they depart at or after that booking time.
- Each offer has the prices of the time of the booking: the newest price at or before the booking time.
- The page shows the hour values at which your booked offer had the lowest effective cost of its trip. The most
  bookings that share one interval give the suggestion, for example "Your bookings fit an hour value from €20 to €40
  (2 of 2 bookings)". An interval with no upper end shows "from €20", and one with no lower end shows "up to €40".
- When no booking can be compared, the page shows "No bookings to compare yet" and no button.
- "Use this hour value" sets the hour markup of the profile to the suggested value. For a closed interval this is
  the middle; for an open interval it is the end that is given. The value is rounded to cents and kept between 0
  and 100. The page computes the value again on the server, and then shows the new value in "Hour markup €/h".

#### Hour tiers

The time cost can have up to two more hour rates, by the length of the trip. Set them under "Advanced" in the
"Hour tiers" group:

- **Tier 1 from min** and **Tier 2 from min**: the trip time, in minutes, from which the tier starts. A value of 0
  turns the tier off.
- **Tier 1 €/h** and **Tier 2 €/h**: the rate, in euro per hour, of that tier.

The tiers are marginal, like the tax brackets of an income. Each hour costs the rate of the band where it falls. The
first band uses the hour markup. For example, with an hour markup of €4/h, Tier 1 from 240 min at €8/h, and Tier 2 from
480 min at €15/h: the first 4 hours cost €4/h, the next 4 hours cost €8/h, and every hour after 8 hours costs €15/h.
A trip of 6 hours costs 4 × 4 + 2 × 8 = €32 of time. A trip of 9 hours costs 4 × 4 + 4 × 8 + 1 × 15 = €63.

### Group trips

A trip has a number of travelers (the field "Travelers", 1 to 9). The score compares one traveler with another.

- **Price per traveler.** For bahn.de, NS International, Flixbus and Kiwi.com, the score uses the price per traveler:
  the group price divided by the number of travelers of the capture.
- **Breakdown.** The breakdown shows the group price, for example `€180 for 2 travelers`, with the parts of one traveler.
- **Warning.** A capture for another number of travelers than the trip gets a warning. The panel shows "These offers are
  for 2 travelers; the trip has 1". The captures page `/captures` shows the same warning in the column of the trip.
- **Manual entry.** The manual entry form has the field "Price for N travelers". Enter the group price there.

### Door-to-door

The effective cost also counts the time and cost outside the vehicle. The breakdown shows each part on its own.

- **Access and egress places.** `/places` lists the places that you set. A place has a text, a kind, minutes and a cost.
  Kind `access` is the way from the place to the first station; kind `egress` is the way from the last station to the
  place. A leg matches a place when its station name has the same text (case and outer spaces do not count). An offer
  with a matching access place adds the parts `access time` (minutes × hour markup) and `access cost`. An offer with a
  matching egress place adds `egress time` and `egress cost`. An offer with no matching place adds nothing.
- **Airport time and baggage (flights).** An offer with a flight leg adds two parts. `airport time` is the minutes before
  departure plus the minutes after landing, at the hour markup. The part `baggage` (or `baggage (included)`) depends on the
  fare: a fare with an included checked bag (field `checked_bags_included` of at least 1) gets `baggage (included)` at €0;
  a fare with a known price for the first checked bag (field `checked_bag_price`, for example from kiwi.com) gets that
  price in EUR; every other flight fare gets the baggage fee. A fare with a bag price in a currency with no exchange rate
  gets the baggage fee. The **Advanced** section under the sliders sets the times and the baggage fee. The defaults are
  120 minutes before departure, 30 minutes after landing and a baggage fee of €0. A baggage fee of 0 means no bag: it
  removes the baggage part from the ranking, and a fare with an included bag gets no part too.

### Time of day and night

The **Advanced** section under the sliders also sets the time of day. Each setting has a default. The times are local
times of the stored offset.

- **Early limit (local)**, default `06:00`. A first leg that departs before this time adds the part `early departure`.
- **Late limit (local)**, default `23:30`. A last leg that arrives after this time adds the part `late arrival`.
- **Early or late penalty €**, default `0`. The amount of each of these two parts. A value of 0 removes both parts.
- **Night start (local)**, default `23:00`, and **Night end (local)**, default `06:00`. They set the night window. A window
  that crosses midnight is allowed.
- **Night minutes**, default `240`. An offer that spans at least this many minutes in the night window adds the part
  `night travel`.
- **Night travel € (negative = bonus)**, default `0`. The amount of the `night travel` part. A negative value is a bonus.
  A value of 0 removes the part.
- **Night in a seat €**, **Night in a couchette €** and **Night in a sleeper €**, under "Advanced", default empty. Each
  value is the night adjustment of one berth of a night train. Empty means the night travel adjustment above. The
  Nightjet tiers of oebbtickets.at give the berth (seat, couchette, sleeper). The breakdown shows the part
  `night in a seat`, `night in a couchette` or `night in a sleeper` instead of `night travel`.
- **Night hour markup €/h**, default empty. Empty means the same as the hour markup. A value sets the hour markup inside
  the night window. The difference to the hour markup adds the part `night hours` for the night minutes.
- **Overnight stop: minimum night minutes**, default `240`, and **Overnight stop: hotel cost (€)**, default `0`. In the
  section "Advanced". A transfer with at least the minimum night minutes adds the hotel cost as the part
  `overnight stop in <place>`. A cost of 0 adds no part.

### Arrive by

The trip form has the field **Arrive by**: the local time at the destination. An empty field means no time. The trip page shows "Arrive by 14:00" under the title.

- The trip page hides each offer whose last leg arrives after this time, on the day of its departure. A `latest_arrive` value in the query replaces this time. An empty `latest_arrive` shows all offers.
- **Wait before the arrival time, € per hour**, in "Advanced", default `0`. An offer that arrives before the time costs the waiting hours at this rate. The breakdown shows the part "wait 3 h 30 min before 14:00". An arrival at or after the time adds no part. A value of 0 removes the part.

### Hour value per mode

The **Advanced** section under the sliders has four fields, one for each mode: **Train hour €**, **Bus hour €**,
**Flight hour €** and **Ferry hour €**. Each field is empty by default, and an empty field means the hour markup. A value
gives the legs of that mode their own hour value. The breakdown shows the difference to the hour markup as the part
`<mode> hours` (for example `train hours`), for the minutes of the legs of that mode. A value equal to the hour markup
adds no part. The part `airport time` of a flight uses the **Flight hour €** value too, when it is set.

### Risk

The **Advanced** section under the sliders also sets the risk extras. Each setting has a default. A value of 0 removes
its part from the ranking. Each part shows its own label in the breakdown.

- **Short transfer minutes**, default `10`. A transfer is short when it lasts less than this many minutes. A transfer
  is the time from the arrival of one leg to the departure of the next leg.
- **Short transfer penalty €**, default `0`. The part `short transfer` is this amount times the count of short transfers.
- **Change of station: minimum minutes**, default blank. A transfer where you change station is short when it lasts
  less than this many minutes, for the short-transfer count. A transfer without a change of station uses "Short
  transfer minutes". When this field is blank, a change of station uses "Short transfer minutes" too.
- **Change of station penalty €**, default `0`. The part `change of station` is this amount times the count of changes
  of station. A transfer counts as a change of station when the leg before it arrives at another station than the leg
  after it departs from. The expanded row shows the change as "Change of station: A → B". Split tickets use the same rule.
- **No later connection penalty €**, default `0`. The part `no later connection` is this amount times the count of
  transfers with no later connection. A transfer has a later connection when another captured itinerary of the trip
  departs later from the place of the transfer and ends at the final station of the itinerary. Only the captured
  itineraries of the trip count, and only those that have not departed yet (also the hidden ones). The expanded row
  shows "· no later connection captured" after each such transfer. The mark shows also when the penalty is `0`. A value of 0 removes the part.
- **Train markup €**, **Bus markup €**, **Flight markup €** and **Ferry markup €**, each default `0`. An itinerary that
  uses the mode adds the part `<mode> markup` once. A negative amount is a discount.
- **Carriers**, in "Advanced": three slots, each with **Carrier n name** and **Carrier n markup €**. The default is no name
  and a markup of `0`, so no slot adds a part. A leg whose carrier is the name of a slot adds the part `carrier <name>`
  with the markup, once per itinerary. The name matches without case and outer spaces. A negative markup is a discount.
- **Transfer place 1 to 3**, in "Advanced", fieldset "Transfer places": three slots, each with the label **Transfer place n**
  (the name) and **Transfer markup n € (negative = discount)** (the markup). This markup is not the slider **Transfer markup €**,
  which sets the markup for each transfer at any place. The default is no name and a markup of `0`, so no slot adds a part. A transfer at a place of a slot adds the markup, and the
  breakdown shows the part `transfer at <name>` with the amount. A transfer is at a place when the arrival station of the leg
  before it, or the departure station of the leg after it, contains the slot name. The name matches without case
  and outer spaces, for example `Brussels-Midi` or `Paris CDG`. Two transfers at one place add the markup two times.
  A negative markup is a discount.
- **Non-refundable fare €**, **Partly refundable fare €** and **Flexible fare €**, each default `0`. A fare of that tier
  adds the part `non-refundable`, `partly refundable` or `flexible`. A negative amount is a bonus. The tier comes from
  the `flexibility` text of the offer. The text `non_refundable`, `nonrefundable`, `no_refund` or `saver` gives
  non-refundable. The text `partly_refundable`, `partially_refundable` or `semi_flexible` gives partly refundable.
  The text `flexible`, `flex`, `refundable` or `fully_refundable` gives flexible. Any other text, or no text, adds nothing.
- **1st class €/hour**, default `0`. The part `1st class` is this amount times the hours of the itinerary, for a fare of the
  travel class `first` only (see "API"). A negative amount is a bonus, so it lowers the effective cost of a 1st class fare.
  A value of 0 removes the part.
- **Self-transfer €**, default `0`. The part `self-transfer` is this amount times the count of self-transfers of the fare.
  The count comes from the `ticket` field of the legs (see "API").

### CO₂

The ranking can count the CO₂ of an offer as a cost. The estimate is per traveler: the hours of each leg times the kg of
CO₂ per hour of its mode. The defaults are 3 kg per hour for train and ferry, 2 kg for bus and 90 kg for flight. The
**Advanced** section under the sliders sets these values and **CO₂ price € per kg**, which has the default `0`.

- With a price of 0, the CO₂ adds no part to the effective cost. The row still shows "CO₂ about N kg per traveler (estimate)".
- With a price above 0, the breakdown shows the part `CO₂ <n> kg`, for example `CO₂ 180 kg`. Its amount is the kg times
  the price per kg.

### Stale offers

An offer is stale when its newest capture is older than **Stale after hours**, default `24` (from 1 to 720).
The setting is in the **Advanced** section under the sliders. A stale row shows "stale, price may have changed".
The flag only informs you: it does not change the price.

- **Stale penalty €**, default `0`. The part `stale` is this amount for each stale offer. It adds to the cost of the
  offer, and the breakdown shows it. The value is at most 1000. A value of 0 does not change the ranking.
- A score profile stores both values (see "Score profiles").
- To hide the stale offers, tick the checkbox "hide stale" above the table. The rows that stay visible are the only
  rows that the badges and the highlights use.

### Exchange rates

A fare in another currency than EUR is ranked by its EUR value. Store the rates on `/rates` (link "Exchange rates"
on `/settings`):

- Enter a 3-letter code (not `EUR`) and the value in EUR of one unit, for example `CHF` and `1.07`. A save of an
  existing code changes its rate. The list shows each rate with the time of its last change.
- To remove a rate, press "Delete" on its row.
- Bad input shows an error and stores nothing. The code must be 3 letters and not `EUR`. The rate must be a number
  more than 0 with at most 6 decimals.

On a trip page, the breakdown of a fare in another currency shows its price in that currency and its EUR value.
The effective cost uses the EUR value. The sort by price, "cheapest" and the compare page use the EUR value too.

If a fare has no rate for its currency, its row shows **no rate for XXX** with a link "Add a rate" to `/rates`. Such a
row has no cost and sorts after the rows with a cost.

The trips list `/` shows the lowest EUR value of the fares of each trip. A trip with only fares without a rate shows
its lowest price in its currency with "no rate". A journey with a fare that has no rate shows "no total".

### Booking fees

A source can add a fee to each booking, for example the fee of a booking site. Set the fees on `/fees` (link "Booking
fees" on `/settings`):

- Choose a source in the list "Source" and enter the fee in EUR in "Fee (€)". Then press "Save fee". The table "Fees"
  shows each source and its fee.
- The default fee of each source is €0.00.
- A fee must be a number from 0 to 1000 with at most 2 decimals, for example `1.50`. Another value shows the error
  "The fee must be a number from 0 to 1000 with at most 2 decimals." and stores nothing.
- A fee of 0 removes the fee of the source.

A fee changes the effective cost and the main fare of the offers of its source. The breakdown of an offer shows the
part "<source name> fee", for example "Trainline fee €1.50". A fee of 0 adds no part. On a trip for 2 or more
travelers, the part is the fee divided by the number of travelers, as the price is per traveler.

Example: an ICE has a fare of €90.00 from bahn.de and a fare of €89.00 from Trainline. With a Trainline fee of €1.50,
the Trainline fare costs €90.50. The bahn.de fare then is the main fare. With a Trainline fee of €0, the Trainline
fare is the main fare.

The fees apply on all pages that rank the offers: the trip page, the compare page, the shared trip, the CSV export and
the best offer of the userscript panel.

## Development

You need Python 3.12 and PostgreSQL 16 for the tests.

```bash
python3 -m pip install -r requirements-dev.txt
ruff check .
python3 -m pytest -n auto
```

The `Makefile` has these targets: `up`, `down`, `logs`, `test`, `migrate`, `backup` and `restore` (`FILE=<backup file>`).

The code: `app/` (FastAPI), `tests/` (pytest). The planned layout is in [`CLAUDE.md`](CLAUDE.md), section "Code map".

## How the project is built

AI agents (Claude Code) build this project from the roadmap, with the agent system in `framework/`. They take the
tickets (GitHub issues), make a pull request for each ticket and merge it when CI is green. The owner steers with
issues, [`steering/project/PRINCIPLES.md`](steering/project/PRINCIPLES.md) and the roadmap.

## License

GPL-3.0. See [`LICENSE`](LICENSE).
