# Roadmap

The goals of travel-aggregator and their features: done (`[x]`) or missing (`[ ]`). The `roadmap` skill makes the next epic from a missing feature.

The source of the goals: the project specification of the owner (2026-11-06), milestones 1 to 5. The MVP is
milestones 1 to 3: `capture:skeleton` to `capture:bahn`, `rank:base` to `rank:profiles`, `trip:list` and `trip:table`.

## 1. Capture offers while I browse

- [ ] `capture:skeleton` Walking skeleton: `docker compose up` (app + db), Alembic migrations at start, an API token, `POST /api/ingest` with normalized offers, the offers in a list on the trip page
  - `docker compose up` starts `app` and `db`, and `GET /api/health` answers "ok"
  - A POST with a valid token shows its offers on the trip page; a request with a bad token gets 401
  - Each green CI on `main` pushes the image `:preview` (job `preview` of `.github/workflows/ci.yml`), and `travel-preview.larspolo.nl` runs it within 5 minutes (`deploy/preview/`); `/api/health` shows its commit (`GIT_SHA`)
- [ ] `capture:upsert` Idempotent upsert by itinerary fingerprint, price history, the raw capture stored compressed, the counts in the response
  - The same itinerary sent twice gives 1 itinerary and 2 price rows
  - One bad offer is rejected and the other offers of the batch are stored (`{created, updated, unchanged, rejected, errors[]}`)
- [ ] `capture:manual` Manual entry form for offers from sites with no userscript
  - An offer from the form shows in the ranked list as a captured offer does
- [ ] `capture:userscript` Shared userscript core: floating panel, trip dropdown, "+ new trip", auto-send on by default, queue and retry, config menu, `GM_xmlhttpRequest`; the API tokens page (create, revoke, config snippet)
  - The panel shows "Captured N offers → sent ✓" or a clear error
  - Payloads that were not sent go again later, with no lost offer
- [x] `capture:bahn` (#151) bahn.de: JSON interception, server parser, trimmed fixtures, fail-soft parsing, "reparse capture"
  - A search on bahn.de shows all fare classes on the trip page within seconds, with no manual step
  - After a parser fix, "reparse" of a stored capture gives the correct offers
- [ ] `capture:ns` NS International: userscript, server parser, trimmed fixtures
  - A search on NS International shows its fares on the trip page
- [ ] `capture:flixbus` Flixbus: userscript, server parser, trimmed fixtures
  - A search on Flixbus shows its offers on the trip page
- [ ] `capture:flight` One flight source: the one that is easiest to intercept (the agents compare and record why), userscript, server parser, trimmed fixtures
  - A flight offer and a train offer for the same trip show in one list

## 2. Rank offers by effective cost

- [ ] `rank:base` Base formula (price + hours × hour_markup + transfers × transfer_markup), a breakdown per row, sliders with live re-ranking
  - A slider change re-ranks the list at once
  - Each row shows its breakdown ("€90 price + €62 time + €30 transfers = €182")
- [ ] `rank:door` Door-to-door: access and egress places (time and cost), airport buffer, baggage fee
  - A flight and a train for the same trip compare on door-to-door effective cost
- [ ] `rank:time` Night travel bonus or penalty, time-of-day penalty windows, different hour values for day and night
  - A departure before the early limit shows its penalty in the breakdown
- [ ] `rank:risk` Penalties for short transfers and self-transfers, flexibility tiers, mode preference
  - A transfer shorter than N minutes shows its penalty in the breakdown
- [ ] `rank:filters` Hard filters: max transfers, max duration, earliest departure, latest arrival, excluded carriers and modes
  - An excluded offer does not show in the list; a penalized offer shows lower
- [ ] `rank:profiles` Named profiles, one default, an override per trip, "save as profile"
  - A change of the profile re-ranks the trip page at once
- [ ] `rank:stale` Offers that were not captured again for N hours get a "stale" flag and an optional penalty
  - A stale offer shows "stale, price may have changed"

## 3. Plan a trip in one place

- [ ] `trip:list` Single-user login (session and CSRF), the trips list (route, dates, offer count, best offer, status), create and edit a trip
  - A page or a form with no login goes to the login page
- [ ] `trip:table` The full ranked table: mode icons, "+1 day" mark, freshness, sort, filters, highlights (cheapest, fastest, best value), expandable rows (legs, transfer times, all fares, booking and search links)
  - The trip page stays fast with 1,000 offers
  - An expanded row shows all fares of all sources of its itinerary
- [ ] `trip:manage` Pin, hide, mark as booked, a note per itinerary
  - A pinned itinerary stays at the top; a hidden one shows only with "show hidden"
- [ ] `trip:history` A price history chart per fare
  - Two captures with different prices show as two points of the chart
- [ ] `trip:compare` Compare 2 to 4 offers side by side
- [x] `trip:mobile` (#310) A responsive layout of all pages
  - All pages work at a phone width of 390 px with no horizontal scroll (agents check with screenshots; the owner then tests on a phone)
- [ ] `trip:links` Search links per source, filled with the values of the trip (they only open a page; they fetch nothing)

## 4. Run it on my home server

- [ ] `host:deploy` Production setup: multi-stage image with a non-root user, healthcheck, `.env.example`, configurable port, Caddy, nginx and Traefik examples; at the end of each epic a tagged Docker image on GHCR and the tag `:latest`
  - The owner's real instance follows `:latest` (it moves only when an epic closes) behind the reverse proxy with HTTPS
  - A migration that drops or changes data makes a backup first
- [ ] `host:backup` `pg_dump` backup and restore, a `Makefile` (up, down, logs, test, migrate, backup)
  - A restore of a backup gives back all trips and the price history
- [ ] `host:retention` Cleanup of raw captures after the retention period, with the setting in the UI
  - A capture older than the period is deleted; its offers and prices stay
- [ ] `host:docs` Setup guide: install, reverse proxy, userscripts, tokens, backup
  - A new user can follow the guide from an empty server to a first captured offer
