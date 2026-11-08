# eurostar.com fixtures

Trimmed captures of the search responses of `POST https://site-api.eurostar.com/gateway`: the GraphQL gateway of the
Eurostar site. The userscript hooks this endpoint and reads the body of the operation `NewBookingSearch` (the journey
search of the page). The other operations of the same endpoint (`FareConditions`, `CheapestFaresSearch`) are not kept.

Source: the HAR files of #954 (branch `owner/eurostar-captures`, files `captures/eurostar.com/954-eurostar-954-1.har`
and `954-eurostar-954-2.har`). The capture date is 2026-11-08.

Each file has `url`, `request` (only the method and the JSON body: `operationName` and `variables`; the GraphQL `query`
text and the headers are removed) and `response` (the JSON body: `data.journeySearch.outbound`).

Each search is a full page load of `https://www.eurostar.com/search/uk-en?adult=1&origin=<uic>&destination=<uic>&outbound=2026-12-01`.
The searches are one way, for Tue 2026-12-01, for 1 adult. The prices are in GBP.

| File | Search (UIC codes of the request) | What it shows |
|---|---|---|
| `search-amsterdam-london.json` | Amsterdam Centraal (`8400058`) → London St Pancras Int'l (`7015400`) | 3 journeys: 06:40 (train 9115, direct), 07:10 (9316 from Amsterdam, then 9123 from Brussels Midi: 1 transfer in Brussels), 18:40 (9167, direct). |
| `search-brussels-paris.json` | Brussels Midi (`8814001`) → Paris Nord (`8727100`) | 3 journeys: 08:13 (9410) and 08:13 (9310), the same times with two train numbers, and 18:13 (9370). The PREMIER fare of 9370 is sold out: `displayPrice` is `null` and `seats` is 0. |

The other journeys of the two searches (11 in the Amsterdam search, 32 in the Brussels search) are removed. The
journeys that are kept have all their fares (`STANDARD`, `PLUS` and `PREMIER`).

Notes for the parser:

- **Times**: the `timing` of a journey and of a leg has `departureTime` and `arrivalTime` as local times of the station,
  with no offset. The `isoDate` of a leg ends in `Z`, but it is the local time too: do not use it.
- **Prices**: `prices.displayPrice` is a JSON number in GBP. It is `null` when the fare is sold out.
- **Classes**: `fares[].classOfService.code` is `STANDARD`, `PLUS` or `PREMIER`. `seats` is the number of seats left.
- **Legs**: `fares[].legs` lists the legs of the journey in order. Each leg has `origin`, `destination`, `serviceName`
  (the train number), `serviceType`, `timing` and `flexibilityLevel`.
- **Passengers**: the `passengerAgeGroup.age` of each product is `REDACTED` in these files (the age of the search is
  personal data, P5). The parser must not read it.

The files have no names, no e-mail addresses, no customer ids, no cookies and no tokens. Each file is under 30 kB.
