# Project: Personal Travel Options Aggregator

## 1. Goal

A self-hosted web application that collects travel options (trains, buses, flights) which I find while browsing travel sites, stores them centrally, and ranks them by a personal "effective cost" so I can compare everything for a trip in one place.

Data enters through **userscripts (Tampermonkey)** that run on the travel sites while I browse and push what they see to my application's **ingest API**. The application has no scraping of its own: I search on bahn.de, a flight site, etc., and the userscript captures the results of that search.

### Why capture-while-browsing
- Sites are hard to scrape server-side (bot detection, sessions, JS-rendered). My own browser already has the data.
- Passive capture of pages I visit myself is low-volume and doesn't hammer anyone's servers. **No automated crawling, no mass queries.**
- Result: a "Trip" page that merges bahn.de + NS International + Flixbus + flights into one ranked list.

## 2. Core Concepts

- **Trip**: what I want to do. Origin, destination, date (or date window), number of travelers, notes, status (planning / booked / archived). Everything is attached to a Trip.
- **Offer**: one purchasable way of making the journey. Has a price, legs, source, and capture time.
- **Leg**: one segment (train number / flight number / bus), with departure/arrival place + time (timezone-aware), operator, mode.
- **Score profile**: a named set of weights (my preferences). Ranking is computed from an Offer + a Profile.
- **Capture**: the raw payload as received from the userscript, stored for re-parsing and debugging.

## 3. Architecture

```
[Browser + Tampermonkey userscripts]  --HTTPS POST (JSON, API token)-->  [Ingest API]
                                                                              |
                                                                       [Database]
                                                                              |
                                                          [Web UI: trips, ranked offers]
```

### Stack (fixed)
- Backend: Python 3.12+ with FastAPI (uvicorn), Pydantic for validating the ingest payloads. Keep dependencies few.
- Database: PostgreSQL 16 in its own container. SQLAlchemy 2.x for data access, Alembic for migrations.
- Frontend: server-rendered pages (Jinja2) + htmx/Alpine.js or vanilla JS. No SPA build chain, no Node needed to build the image.
- Userscripts: plain JavaScript, one shared core snippet + one parser per site.
- Deployment: Docker only (no Nix).
  - `Dockerfile`: multi-stage, slim Python base image, non-root user.
  - `docker-compose.yml`: services `app` and `db`, a named volume for the Postgres data, config via `.env` (provide `.env.example`), healthcheck on `/api/health`, `app` published on a configurable port so I can put it behind my existing reverse proxy for HTTPS (include an example Caddy and nginx snippet).
  - Alembic migrations run automatically on container start.
  - A documented `pg_dump` backup/restore command and a small `Makefile` (up, down, logs, test, migrate, backup).
- Tests: pytest, run inside the container (`docker compose run --rm app pytest`).

## 4. Data Capture (Userscripts)

### 4.1 Strategy per site, in order of preference
1. **Intercept the site's own JSON responses** (hook `fetch` and `XMLHttpRequest`, run at `document-start`, use `unsafeWindow` / `@grant unsafeWindow`). Structured, stable, far better than DOM scraping. Sites like bahn.de load results via internal JSON APIs.
2. **Read embedded state** (`__NEXT_DATA__`, `window.__INITIAL_STATE__`, JSON-LD).
3. **DOM scraping** as last resort, with defensive selectors.

Never call the sites' APIs myself with replayed requests; only observe what the page already requested.

### 4.2 Userscript UI (small floating panel on each supported site)
- Shows: "Attach to trip: [dropdown of my active trips ▾] [+ new trip]" (fetched from `GET /api/trips`).
- Toggle: auto-send / manual send.
- Status line: "Captured 14 offers → sent ✓" or an error.
- The currently selected trip is remembered (`GM_setValue`).
- Default: auto-send captured offers to the selected trip, because forgetting to click is the main usability failure.

### 4.3 Userscript responsibilities
- Detect results, convert to the **common ingest format** (section 5), POST in batches.
- Include the search page URL (deep link back), site name, parser version, capture timestamp, and the raw payload (or a trimmed version) for re-parsing.
- Keep all parsing logic on the server too if possible: the userscript may send raw JSON and a `source` identifier, and the server has a parser per source. **Preferred**, because fixing a parser then needs no userscript reinstall. Fall back to client-side normalization only where raw data is too large.
- Handle failures gracefully: queue unsent payloads in `GM_setValue` and retry.
- Config (server URL, API token) set once via `GM_registerMenuCommand`.
- Use `GM_xmlhttpRequest` for cross-origin POSTs to my server (avoids CORS/CSP issues on the travel sites).

### 4.4 Initial sources
| Source | Mode | Notes |
|---|---|---|
| bahn.de | train | Multiple fares per connection (Sparpreis, Flexpreis, etc.). Capture all fare classes. |
| NS International | train | International fares |
| Flixbus | bus | |
| One flight source (e.g. Google Flights, Skyscanner or Kayak) | flight | Choose the one with the easiest-to-intercept data |
| Generic "manual entry" form in the web UI | any | For things I find that no script covers |

New sources must be added by writing one userscript + one server parser, nothing else.

### 4.5 Later: browser extension
Only if userscripts prove limiting (e.g. need for background tabs, cross-site orchestration). Design the ingest API so that an extension can use it unchanged. A "search helper" may later generate prefilled search links for each source for a given Trip (not automated fetching, just convenient opening).

## 5. Ingest API

Authentication: `Authorization: Bearer <token>`, tokens stored hashed, revocable. CORS not required if using `GM_xmlhttpRequest`. Rate limit modestly. Validate everything.

### Endpoints
- `GET /api/trips?status=planning` – list for the userscript dropdown
- `POST /api/trips` – create a trip
- `POST /api/ingest` – submit captured data (below)
- `GET /api/health`

### `POST /api/ingest` body
```json
{
  "trip_id": 12,
  "source": "bahn.de",
  "parser_version": "1.3.0",
  "captured_at": "2026-11-03T19:41:00Z",
  "page_url": "https://www.bahn.de/...",
  "search_context": { "from": "Amsterdam", "to": "Zürich", "date": "2026-12-20", "travelers": 1 },
  "raw": { },
  "offers": [
    {
      "external_id": "optional-site-id",
      "price_amount": 89.90,
      "price_currency": "EUR",
      "fare_name": "Sparpreis",
      "flexibility": "non_refundable",
      "legs": [
        { "mode": "train", "carrier": "DB", "service_no": "ICE 77",
          "from_name": "Amsterdam Centraal", "from_code": null,
          "to_name": "Basel SBB", "to_code": null,
          "depart_at": "2026-12-20T07:34:00+01:00",
          "arrive_at": "2026-12-20T14:02:00+01:00" }
      ],
      "booking_url": "https://..."
    }
  ]
}
```
Either `raw` (server parses) or `offers` (pre-normalized) must be present; both allowed.

### Ingest rules
- **Idempotent upsert.** Compute an *itinerary fingerprint* = hash of (mode + carrier + service_no + depart_at + arrive_at for every leg). A re-capture of the same itinerary updates the offer instead of duplicating.
- **Price history.** One row per (offer, fare, captured_at, price). Never overwrite prices, so I can see price trends. The "current price" is the latest capture.
- **Multiple fares per itinerary**: one Itinerary → many Fares. Ranking is per Fare (cheapest fare of an itinerary is the main row, others expandable).
- Store the raw capture (compressed) with retention setting (e.g. 90 days).
- Return counts: `{created, updated, unchanged, rejected, errors[]}`.
- Everything timezone-aware; store UTC + original offset.

## 6. Data Model (suggested)

- `trips(id, title, origin_text, destination_text, date_from, date_to, travelers, status, notes, created_at)`
- `captures(id, trip_id, source, parser_version, page_url, search_context_json, raw_json, captured_at)`
- `itineraries(id, trip_id, fingerprint UNIQUE per trip, mode_summary, depart_at, arrive_at, duration_min, transfers, first_seen_at, last_seen_at, hidden, pinned, note)`
- `legs(id, itinerary_id, seq, mode, carrier, service_no, from_name, from_code, to_name, to_code, depart_at, arrive_at, ...)`
- `fares(id, itinerary_id, source, fare_name, flexibility, booking_url, latest_price, currency, latest_captured_at)`
- `fare_prices(id, fare_id, price, currency, captured_at, capture_id)` – history
- `score_profiles(id, name, is_default, config_json)`
- `access_times(id, place_text, kind, minutes, cost)` – door-to-door extras (see 7.2)
- `api_tokens(id, name, token_hash, last_used_at, revoked_at)`

Derived values (duration, transfers, transfer minimum) are computed at ingest and stored; the **score is computed at query time** from the active profile (cheap at this scale) so changing preferences re-ranks instantly.

## 7. Ranking

### 7.1 Base formula
```
effective_cost = price
               + travel_hours * hour_markup
               + transfers * transfer_markup
               + (extras below)
```
Lower is better. All markups are in my currency (EUR) and are editable in the UI with sliders and live re-ranking. Show a **breakdown** per row ("€90 price + €62 time + €30 transfers + €15 night = €197") so the ranking is explainable and I can tune the weights.

### 7.2 Extras (each is a configurable weight; 0 disables it)
- **Door-to-door time**: add an *access/egress* time and cost per departure/arrival place (e.g. "home → Amsterdam Centraal 35 min, €0"; "Zürich Flughafen → my destination 15 min, €4.5"). Crucial for fair flight-vs-train comparison. Flights additionally get an **airport buffer** (e.g. 120 min before departure, 30 after landing) and a **baggage fee** estimate if a bag is needed.
- **Night travel**: night trains/buses can get a bonus or penalty (sleep saves a hotel night; configurable as negative cost), plus time-of-day penalty windows (e.g. departures before 06:00 or arrivals after 23:30 cost +€X).
- **Risky transfers**: penalty per transfer shorter than N minutes, and extra penalty for transfers in the same itinerary across different tickets (self-transfer).
- **Flexibility**: bonus for refundable/flexible fares, penalty for non-refundable (€ per tier).
- **Mode preference**: flat markup/discount by mode (e.g. bus +€20, flight +€X for CO₂ preference).
- **Time value variation**: optional different hour_markup for daytime vs. awake-overnight hours.
- **Price staleness**: offers not re-captured for > N hours are flagged "stale, price may have changed" and optionally penalized by a small amount.
- **Hard filters** (exclude, don't just penalize): max transfers, max duration, earliest departure, latest arrival, excluded carriers/modes.

Profiles: multiple named profiles ("Cheap", "Comfort", "Business"), one default; per-trip override.

## 8. Web UI

1. **Trips list**: title, route, dates, count of offers, best offer so far, status.
2. **Trip page (main screen)**:
   - Ranked table: rank, mode icons, times (dep → arr, +1 day marker), duration, transfers, cheapest fare, effective cost, source(s), freshness ("captured 2h ago").
   - Expand a row: legs with times and transfer durations, all fares/prices from all sources, price history chart, breakdown of the score, note field, "open booking page" link and "open search" link.
   - Sort by score (default), price, duration, departure.
   - Filters: mode, max transfers, time windows, source, hide stale.
   - Weight panel (sliders/inputs) with live re-ranking; profile switcher; "save as profile".
   - Pin / hide / mark "booked".
   - Highlights: cheapest, fastest, best score ("best value").
3. **Compare view**: select 2–4 offers, show side by side.
4. **Manual entry form** for offers from sites without a userscript.
5. **Settings**: profiles, access-time places, API tokens (create/revoke, shows the userscript config snippet), data retention.
6. Responsive (I will check on mobile), dark mode optional, fast with ~1,000 offers per trip.
7. Auth: simple single-user login (password + session, or HTTP basic behind HTTPS). It is a personal tool, not multi-tenant.

## 9. Non-functional Requirements

- **Security**: HTTPS only; hashed tokens; CSRF protection for UI forms; strict input validation and size limits on ingest; parameterized queries; escape all output (captured data is untrusted).
- **Privacy**: no third-party analytics. Don't capture or store login credentials, cookies, passenger names, or payment data. Userscripts must only read result data.
- **Robustness**: parsers fail soft (one bad offer doesn't discard the batch); every failure logged with the capture id so it can be reparsed after a fix.
- **Maintainability**: per-source parser classes with a common interface and **fixture-based tests** (saved real raw payloads under `tests/fixtures/<source>/`). A "reparse capture" admin action reruns the current parser on stored raw data.
- **Backups**: documented `pg_dump` routine for the Docker setup (see section 3).
- **Legal/ToS note**: tool only processes data the user views in their own browser; no scheduled/automated requests to third-party sites. Keep it that way.

## 10. Milestones

1. **Foundation**: DB schema + migrations, token auth, `POST /api/ingest` accepting the normalized format, trips CRUD, manual entry form, basic ranked table with the base formula and weight sliders.
2. **First real source**: bahn.de userscript (JSON interception) + server parser + fixtures + tests; trip dropdown in the userscript panel; dedupe/upsert and price history.
3. **Ranking depth**: access times (door-to-door), night/time-of-day penalties, transfer risk, flexibility, hard filters, profiles, score breakdown.
4. **More sources**: NS International, Flixbus, one flight source, with flight-specific handling (airport buffer, baggage).
5. **Polish**: compare view, price history charts, pin/hide/booked, staleness flags, retention cleanup, mobile layout, setup documentation.
6. **Optional**: browser extension, search-link generator per trip, price-drop notifications (email/push) for pinned offers.

## 11. Acceptance Criteria (MVP = milestones 1–3)

- I install the bahn.de userscript, pick a trip, search a connection on bahn.de, and within seconds the offers appear on the trip page without any manual step.
- Searching the same route again later does not duplicate itineraries but records new prices in the history.
- Changing hour_markup or transfer_markup re-ranks the list immediately and the breakdown explains each score.
- A flight and a train offer for the same trip are comparable on door-to-door effective cost.
- A malformed payload returns a clear error and does not corrupt data; a stored raw capture can be reparsed after a parser fix.
- All parsers have fixture tests that pass; the ingest API has tests for auth, validation, and idempotency.

## 12. Out of Scope

Booking or payment automation, automated background crawling, multi-user accounts, price prediction, mobile apps.

## 13. Open Questions for the Implementer to Decide and Document

- Which flight site is easiest to capture reliably.
- Whether raw payloads are sent to the server (preferred) or normalized in the userscript, per source.
- Exact handling of round trips and multi-city trips (suggested: treat outbound and return as two Trips linked by a parent, MVP supports one-way only).
