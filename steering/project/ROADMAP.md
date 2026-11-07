# Roadmap

The goals of travel-aggregator and their features: done (`[x]`) or missing (`[ ]`). The `roadmap` skill makes the next epic from a missing feature.

The source of the goals: the project specification of the owner (2026-11-06), milestones 1 to 5. The MVP is
milestones 1 to 3: `capture:skeleton` to `capture:bahn`, `rank:base` to `rank:profiles`, `trip:list` and `trip:table`.

## 1. Capture offers while I browse

- [x] `capture:skeleton` (#2) Walking skeleton: `docker compose up` (app + db), Alembic migrations at start, an API token, `POST /api/ingest` with normalized offers, the offers in a list on the trip page
  - `docker compose up` starts `app` and `db`, and `GET /api/health` answers "ok"
  - A POST with a valid token shows its offers on the trip page; a request with a bad token gets 401
  - Each green CI on `main` pushes the image `:preview` (job `preview` of `.github/workflows/ci.yml`), and `travel-preview.larspolo.nl` runs it within 5 minutes (`deploy/preview/`); `/api/health` shows its commit (`GIT_SHA`)
- [x] `capture:upsert` (#25) Idempotent upsert by itinerary fingerprint, price history, the raw capture stored compressed, the counts in the response
  - The same itinerary sent twice gives 1 itinerary and 2 price rows
  - One bad offer is rejected and the other offers of the batch are stored (`{created, updated, unchanged, rejected, errors[]}`)
- [x] `capture:manual` (#117) Manual entry form for offers from sites with no userscript
  - An offer from the form shows in the ranked list as a captured offer does
- [x] `capture:userscript` (#26) Shared userscript core: floating panel, trip dropdown, "+ new trip", auto-send on by default, queue and retry, config menu, `GM_xmlhttpRequest`; the API tokens page (create, revoke, config snippet)
  - The panel shows "Captured N offers → sent ✓" or a clear error
  - Payloads that were not sent go again later, with no lost offer
- [ ] `capture:merge` One itinerary for the same journey from two sources (#481)
  - The same ICE from bahn.de and NS International shows as one row with the fares of both sites
- [x] `capture:reparse-all` (#488) Reparse all failed captures of a source in one step
  - After a parser fix, one button on the failed captures page reparses them all and shows the counts
- [x] `capture:bahn` (#151) bahn.de: JSON interception, server parser, trimmed fixtures, fail-soft parsing, "reparse capture"
  - A search on bahn.de shows all fare classes on the trip page within seconds, with no manual step
  - After a parser fix, "reparse" of a stored capture gives the correct offers
- [x] `capture:ns` (#210) NS International: userscript, server parser, trimmed fixtures
  - A search on NS International shows its fares on the trip page
- [ ] `capture:flixbus` Flixbus: userscript, server parser, trimmed fixtures
  - A search on Flixbus shows its offers on the trip page
- [x] `capture:flight` (#327) One flight source: the one that is easiest to intercept (the agents compare and record why), userscript, server parser, trimmed fixtures
  - A flight offer and a train offer for the same trip show in one list
- [x] `capture:errors` (#345) The captures page shows the result of each parse: the offer count, the rejected count and the errors, with a filter for the failed captures
  - When a site changes its format, the failed captures show with their errors, and "reparse" after a parser fix shows the new result
- [x] `capture:install` (#388) Install and update the userscripts from the app: the app serves its own userscripts and `core.js`, with the install links on the tokens page
  - A click on the install link of the tokens page installs the userscript; after a new image, Tampermonkey updates it to the version of the server
- [x] `capture:match-trip` (#554) A warning when the captured offers do not match the selected trip: the server compares the places and the date of the parsed offers with the trip
  - A capture of Amsterdam → Lisbon into the trip Amsterdam → Zürich shows "These offers do not match the trip" in the panel and on the captures page
- [x] `capture:move` (#578) Move the offers of a capture to another trip, after a capture into the wrong trip
  - "Move to trip" on the captures page moves the offers and their price rows of one capture, and the old trip does not show them

## 2. Rank offers by effective cost

- [x] `rank:base` (#10) Base formula (price + hours × hour_markup + transfers × transfer_markup), a breakdown per row, sliders with live re-ranking
  - A slider change re-ranks the list at once
  - Each row shows its breakdown ("€90 price + €62 time + €30 transfers = €182")
- [x] `rank:door` (#94) Door-to-door: access and egress places (time and cost), airport buffer, baggage fee
  - A flight and a train for the same trip compare on door-to-door effective cost
- [x] `rank:time` (#140) Night travel bonus or penalty, time-of-day penalty windows, different hour values for day and night
  - A departure before the early limit shows its penalty in the breakdown
- [x] `rank:risk` (#172) Penalties for short transfers and self-transfers, flexibility tiers, mode preference
  - A transfer shorter than N minutes shows its penalty in the breakdown
- [x] `rank:filters` (#179) Hard filters: max transfers, max duration, earliest departure, latest arrival, excluded carriers and modes
  - An excluded offer does not show in the list; a penalized offer shows lower
- [x] `rank:profiles` (#228) Named profiles, one default, an override per trip, "save as profile"
  - A change of the profile re-ranks the trip page at once
- [x] `rank:stale` (#274) Offers that were not captured again for N hours get a "stale" flag and an optional penalty
  - A stale offer shows "stale, price may have changed"
- [x] `rank:currency` (#382) Prices in other currencies: exchange rates to EUR in Settings, and the score uses the EUR value
  - A CHF offer ranks by its EUR value, and its breakdown shows the CHF price and the EUR price; an offer in a currency with no rate shows "no rate for CHF"

## 3. Plan a trip in one place

- [x] `trip:list` (#18) Single-user login (session and CSRF), the trips list (route, dates, offer count, best offer, status), create and edit a trip
  - A page or a form with no login goes to the login page
- [x] `trip:table` (#110) The full ranked table: mode icons, "+1 day" mark, freshness, sort, filters, highlights (cheapest, fastest, best value), expandable rows (legs, transfer times, all fares, booking and search links)
  - The trip page stays fast with 1,000 offers
  - An expanded row shows all fares of all sources of its itinerary
- [x] `trip:manage` (#198) Pin, hide, mark as booked, a note per itinerary
  - A pinned itinerary stays at the top; a hidden one shows only with "show hidden"
- [x] `trip:history` (#239) A price history chart per fare
  - Two captures with different prices show as two points of the chart
- [x] `trip:compare` (#291) Compare 2 to 4 offers side by side
- [x] `trip:mobile` (#310) A responsive layout of all pages
  - All pages work at a phone width of 390 px with no horizontal scroll (agents check this with Playwright and screenshots; the owner tests on a phone only the feel)
- [x] `trip:links` (#315) Search links per source, filled with the values of the trip (they only open a page; they fetch nothing)
- [x] `trip:return` (#339) Round trips: an outbound and a return trip linked as one journey (`docs/SPEC.md`, section 13)
  - "Add return trip" makes the linked trip with the swapped places, and each trip page links to the other
  - The trips list shows the two trips together, with the sum of their best offers
- [x] `trip:drops` (#354) Price-drop marks for pinned offers: a new capture with a lower price of a pinned fare shows a mark (in the app; e-mail or push later)
  - The trips list and the trip page show "price dropped €X" for a pinned fare until the owner opens it
- [x] `trip:delete` (#415) Delete a trip with all its offers, prices and captures (`docs/SPEC.md`, milestone 1: trips CRUD)
  - "Delete trip" on the edit page asks for a confirmation; then the trip is not in the trips list, not on its pages and not in the dropdown of the userscript
- [x] `trip:archive` (#486) Archive the past trips: a separate list of the archived trips
  - The trips list does not show an archived trip; "Archived trips (N)" opens them
- [ ] `trip:notify` Price-drop notifications outside the app for the pinned fares (`docs/SPEC.md`, milestone 6), by the channel of the decision #418
  - A new capture with a lower price of a pinned fare sends one notification to the owner's phone
- [ ] `trip:multicity` Multi-city journeys: three or more trips linked in sequence, as `trip:return` links two (`docs/SPEC.md`, section 13)
  - "Add next trip" makes a linked trip from the destination of the last one, and the trips list shows the journey with the sum of the best offers

## 4. Run it on my home server

- [x] `host:deploy` (#83) Production setup: multi-stage image with a non-root user, healthcheck, `.env.example`, configurable port, Caddy, nginx and Traefik examples; at the end of each epic a tagged Docker image on GHCR and the tag `:latest`
  - The owner's real instance follows `:latest` (it moves only when an epic closes) behind the reverse proxy with HTTPS
  - A migration that drops or changes data makes a backup first
- [x] `host:backup` (#134) `pg_dump` backup and restore, a `Makefile` (up, down, logs, test, migrate, backup)
  - A restore of a backup gives back all trips and the price history
- [x] `host:retention` (#205) Cleanup of raw captures after the retention period, with the setting in the UI
  - A capture older than the period is deleted; its offers and prices stay
- [x] `host:docs` (#245) Setup guide: install, reverse proxy, userscripts, tokens, backup
  - A new user can follow the guide from an empty server to a first captured offer
- [x] `host:ratelimit` (#410) A modest rate limit on the API (`docs/SPEC.md`, section 5): per API token, and per address for bad tokens
  - A token that sends more than 120 requests in one minute gets 429 with `Retry-After`; the userscript keeps the payload and sends it later
  - An address that sends 20 bad tokens in 15 minutes gets 429 for 15 minutes
- [x] `host:backup-daily` (#545) A backup of the database each day, the newest backups kept, and the status on the settings page
  - With no manual step, the backups volume has one daily backup per day and not more than `BACKUP_KEEP` of them
  - The settings page shows a warning when the newest backup is older than 48 hours
