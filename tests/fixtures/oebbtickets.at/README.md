# oebbtickets.at fixtures

Trimmed captures of the search and fare responses of `https://shop.oebbtickets.at` (the userscript of #952 intercepts
these paths). Source: the HAR files of #949 (branch `owner/oebb-captures`, files
`captures/oebbtickets.at/949-oebb-949-1-amsterdam-wien-nightjet.har` and `949-oebb-949-2-wien-zuerich.har`). The HAR
files were scrubbed with `tools/capture.py scrub` before the trim. Each file is one JSON response body (no request, no
headers, no cookies). The personal passenger ids are replaced with `1`.

| File | Search (date of travel) | Endpoint (method and path) | Date of capture | What it shows |
|---|---|---|---|---|
| `search-amsterdam-wien.json` | Amsterdam Centraal → Wien Hbf (2026-12-01) | `POST /api/hafas/v4/timetable` | 2026-11-08 | 2 connections: the Nightjet NJ 40421 direct (0 changes), and the Nightjet to Salzburg with one change (RJX to Wien) |
| `fares-amsterdam-wien-nightjet.json` | The Nightjet NJ 40421 of the search above (the offer of the connection with one change) | `POST /api/offer/v6/offers` | 2026-11-08 | The fare tiers of the Nightjet: `offerSections` with the travel classes, the offers (`price`, `flexibility`, `reservation.compartments`) and `passengerPriceDetails` |
| `search-wien-zuerich.json` | Wien Hbf → Zürich HB (2026-12-01) | `POST /api/hafas/v4/timetable` | 2026-11-08 | 2 day connections with changes (2 and 3 changes: RJX, S-Bahn, IR, IC, ICE) |

Notes for the parser:

- **Search response**: `connections[]`. Each connection has `id`, `from` and `to` (`name`, `departure` or `arrival`, local
  time with no offset), `sections[]` (each with `category` and `to`, `from`), `switches` (the number of changes) and
  `duration` (in milliseconds).
- **Fare response**: the offer of one connection. `connection` has the sections. `offerSections[]` has the travel
  classes; `offers` are the fare tiers. The price of an offer is the `price` value.
- **No price**: none of the connections of these captures lacks a price: `GET /api/offer/v1/prices` gives a price for
  each of the 10 connections. So the file set has no connection with no price (the ticket asked for one when the
  response has one).
- **Times**: the times have no offset in these responses. The parser stores each time with its original offset and in UTC.
