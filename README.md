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
| `BACKUP_INTERVAL_HOURS` | The hours between two daily backups of the service `backup` (default `24`) |
| `BACKUP_KEEP` | The number of daily dumps that stay; the older ones are deleted (default `14`, at least `1`) |

To turn on Web Push, run `python3 -m app.notify` once. It prints `VAPID_PUBLIC_KEY=...` and `VAPID_PRIVATE_KEY=...`.
Put both lines and a `VAPID_SUBJECT` in the `.env` file, then restart the app. The settings page then shows the
Web Push buttons. Without these three variables the channel `webpush` is not available.

The image build sets `GIT_SHA` (a build argument of the `Dockerfile`, not a setting): the commit that
`/api/health` shows.

## API

| Method and path | Use |
|---|---|
| `GET /api/health` | `{"status": "ok", "commit": "<commit of the image>"}`. No token. |
| `GET /api/trips` | The trips, newest first; `?status=planning` (or `booked`, `archived`) shows only the trips of that status |
| `POST /api/trips` | Make a trip: `{"title": "...", "origin_text", "destination_text", "date_from", "date_to", "travelers"}` |
| `POST /api/ingest` | Captured offers for a trip (body: [`docs/SPEC.md`](docs/SPEC.md) section 5). Answers `{"created": n, "updated": n, "unchanged": n}` and the field `warning`: the text of the trip warning, or `null` (see "Trip warning of a capture") |

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

All routes but `/api/health` need `Authorization: Bearer <token>` (`python -m app.tokens create NAME`). Bodies are
limited to 5 MB.

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
| `/tokens` | The API tokens: create a token (shown once, with the settings for the userscripts) and revoke a token |
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
- "failed" and "failed (code)": a wrong password, or a wrong code. These rows are marked in orange.

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
A fare of the 1st class shows the badge "1st" after its name. The badge shows in the fare list of each row and on the compare page.
An arrival on a later calendar day shows a mark "+1 day" (or "+2 days" and so on).
Under the fare name, the age of the newest capture shows, for example "2 h ago".
If the newest capture is older than the stale hours, the row also shows "stale, price may have changed". See "Stale offers".
A fare that a newer search of the same site did not show again, in the departure span of that search, shows the mark "not in the last <source> search". The best offer does not use such a fare. The next search that shows the fare again removes the mark.
Click a column header to sort by it. Click it again to reverse the order.
The Mode and Source lists show only one mode or one source.

The hard filters hide the offers that do not match. A penalty does not hide an offer: it only adds to its cost.
Each filter is a query parameter of `/trips/{id}`. An empty value is no filter.
- `max_transfers`: the most transfers (0 to 10).
- `max_duration_min`: the longest duration in minutes.
- `earliest_depart`: the first leg departs at or after this local time.
- `latest_arrive`: the last leg arrives by this local time, on the day of its departure.
- `exclude_mode`: a mode (train, bus or flight) hides each offer with one of its legs.
- `exclude_carrier`: a carrier hides each offer with one of its legs.
- `hide_stale`: the checkbox "hide stale" above the table hides each stale offer. The badges count only the rows that show.
When the filters hide offers, the line "Filters hide N of M offers" shows above the table. It gives the count of each filter, for example "max transfers 1 hides 3", and each filter name is a link to the page without that filter. The line "Best hidden offer" shows the cheapest offer that the filters hide, with its time, route, source and the filters that hide it. Its "Show it" link opens the page without those filters at that row.
The cheapest, fastest and best-value rows show a badge. The badges use the rows after the filters.
Open "Legs and fares" in a row to see its legs, the transfer times and all fares, each with its link.
The expanded row also shows the price history chart of each fare: one point for each capture of the fare.
The route `/trips/{id}/itineraries/{id}/history` shows the same chart and the table of the prices.
The expanded row also shows a break-even line at the top of "Legs and fares": the hour value at which the row and the best
shown row have the same effective cost. For example, `1 h 20 min faster, €3.00 more than the best: better above €12.50/h (yours: €10/h)`.
"Yours" is your hour markup. "Better above €X/h" means that the row is the better one when your hour markup is above
X. "Better below €X/h" means that it is the better one when your hour markup is below X. The best row shows no line,
and a row with no break-even value shows no line. A value from €0/h to €100/h is a link: a click opens the page with that hour markup, so the row is the better one after the click. The value is rounded up for "above" and down for "below". The other weights of the page stay. A value outside this range is text only.

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

### Share a trip read-only

A trip has one read-only link for a travel partner. On `/trips/{id}`, click "Share". The page shows the new link once:
copy it then. Each person with the link sees the offers of the trip, with no login.
The trips list shows the mark "shared" after the trips that have a link.

The shared page `/s/<token>` lists the offers that are not hidden, best effective cost first. Each offer shows the route,
the times, the duration, the transfers, the fare and price, the effective cost with its breakdown, and its legs.
The page uses the profile of the trip. The sliders and filters of the trip page do not apply.
The shared page does not show the notes, the booking links, the price captures or history, the hidden offers, or any
control such as pin, book or delete.

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
"Travel per year" is on the Upcoming page. Only the journeys that you marked as booked are counted.

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
- **Server busy.** When the app answers `429` (too many requests, or too many bad tokens from your address), the panel
  shows `Server busy: kept in the queue`. The offers stay in the queue and the userscript sends them again later.
  See "API" for the limits.

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
  departure plus the minutes after landing, at the hour markup. `baggage` is the baggage fee.
  The **Advanced** section under the sliders sets them. The defaults are 120 minutes before departure, 30 minutes after
  landing and a baggage fee of €0. A value of 0 removes that part from the ranking.

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
- **Night hour markup €/h**, default empty. Empty means the same as the hour markup. A value sets the hour markup inside
  the night window. The difference to the hour markup adds the part `night hours` for the night minutes.
- **Overnight stop: minimum night minutes**, default `240`, and **Overnight stop: hotel cost (€)**, default `0`. In the
  section "Advanced". A transfer with at least the minimum night minutes adds the hotel cost as the part
  `overnight stop in <place>`. A cost of 0 adds no part.

### Arrive by

The trip form has the field **Arrive by**: the local time at the destination. An empty field means no time. The trip page shows "Arrive by 14:00" under the title.

- The trip page hides each offer whose last leg arrives after this time, on the day of its departure. A `latest_arrive` value in the query replaces this time. An empty `latest_arrive` shows all offers.
- **Wait before the arrival time, € per hour**, in "Advanced", default `0`. An offer that arrives before the time costs the waiting hours at this rate. The breakdown shows the part "wait 3 h 30 min before 14:00". An arrival at or after the time adds no part. A value of 0 removes the part.

### Risk

The **Advanced** section under the sliders also sets the risk extras. Each setting has a default. A value of 0 removes
its part from the ranking. Each part shows its own label in the breakdown.

- **Short transfer minutes**, default `10`. A transfer is short when it lasts less than this many minutes. A transfer
  is the time from the arrival of one leg to the departure of the next leg.
- **Short transfer penalty €**, default `0`. The part `short transfer` is this amount times the count of short transfers.
- **Train markup €**, **Bus markup €**, **Flight markup €** and **Ferry markup €**, each default `0`. An itinerary that
  uses the mode adds the part `<mode> markup` once. A negative amount is a discount.
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
