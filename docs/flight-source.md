# The flight source

The project has one flight source (`docs/SPEC.md`, section 4: "Choose the one with the easiest-to-intercept data").
This file compares the captures of #328 and gives the chosen site (#329).

**Chosen site: Kiwi.com.** Parser `source` value: `kiwi.com`. Fixtures: `tests/fixtures/kiwi.com/`.

## The captures

The HAR files are on the branch `owner/flight-captures`. Each search is one way, Tue 1 Dec 2026, 1 adult, economy.

| File | Search | Responses with results |
|---|---|---|
| `captures/kiwi/328-kiwi-328.har` | Amsterdam → Zürich | 3 × `SearchOneWayItinerariesQuery`, 124 KB each |
| `captures/kiwi/328-kiwi-328-2.har` | Amsterdam → Lisbon | 4 × `SearchOneWayItinerariesQuery`, 171 KB each |
| `captures/kayak/328-kayak-328.har` | AMS → ZRH | 7 × `flights/poll`; 3 with results (0.7, 1.1, 4.1 MB) |
| `captures/kayak/328-kayak-328-2.har` | AMS → LIS | 7 × `flights/poll`; 4 with results (0.3, 0.9, 1.1, 3.0 MB) |
| `captures/google-flights/328-google-flights-328.har` | AMS → ZRH | the results page, `ds:1` inline data (43 KB) |
| `captures/google-flights/297-google-flights-297.har` | the capture of #297 | the results page, `ds:1` inline data |

Skyscanner has no capture: the site blocks the search (see the table). The KLM and Transavia files of #297 are
airline sites, not flight search sites; they are not in the comparison.

## The comparison

| Site | Request and loading | Format | Times | Fares, currency, link | Flights, transfers, self-transfers | Baggage | Size and personal data |
|---|---|---|---|---|---|---|---|
| **Kiwi.com** | `POST https://api.skypicker.com/umbrella/v2/graphql?featureName=SearchOneWayItinerariesQuery`. The page polls: 3 or 4 responses per search. Each response has the full list (`limit` 10 of the request); `data.onewayItineraries.metadata.hasMorePending` is `true` until the last response. | GraphQL JSON with named fields (`itineraries[].sector.sectorSegments[].segment`). | Each end of a segment has `localTime` and `utcTimeIso` (UTC). Offset = `localTime` − `utcTimeIso`. No time zone table. | 1 to 2 fares per itinerary: `bookingOptions.edges[].node` with `itineraryProvider.code` (`KIWI-BASIC`, `KIWI`) and `price.amount` (a string, for `Decimal`). The currency is not in the response: it is `variables.options.currency` of the request (`gbp` in the capture). Link: `node.bookingUrl`, relative to `https://www.kiwi.com`. | `segment.carrier.code` + `segment.code` (flight number, for example `HV` `5951`), `operatingCarrier`, `source.station.code` and `destination.station.code` (IATA). Self-transfer: `pnrCount` > 1 (separate tickets), `travelHack.isVirtualInterlining`, and `guarantee: "KIWI_COM"` on the segment after the self-transfer. An airport change is visible (for example LGW → STN). Lisbon: 6 of 10 itineraries are self-transfers. | `bagsInfo`: `includedCheckedBags`, `includedHandBags`, `includedPersonalItem`, and prices in `checkedBagTiers[].tierPrice.amount` and `handBagTiers[]`. | 124 to 172 KB per response. The response has no personal data; it has session tokens (`server.serverToken`, booking tokens). The request has `serverToken` and `searchSessionId`: the userscript must not send them. |
| **Kayak** | `POST https://www.kayak.nl/i/api/search/dynamic/flights/poll`. The page polls: 7 responses per search, `status` `first-phase`, `second-phase`, `complete`; 3 of 7 have 0 results. | JSON with named fields. Results refer by id to the maps `legs`, `segments`, `airports`, `providers`. Ads are in `results` too (`inlineDisplayAd`, `-sponsored` ids). | Only local times (`2026-12-01T06:50:00`). `searchStatus` gives `utcOffset` only for the searched origin and destination, not for transfer airports. The parser needs a table IATA code → time zone (a data file of airports, or a new dependency), and an unknown airport stops the parse of the itinerary. | 1 to 56 fares per itinerary (one per seller): `bookingOptions[].providerCode`, `displayPrice.price` (an integer) and `currency` (`EUR`). Link: `bookingUrl.url`, a relative click-through URL with tracking values. | `segments[id].airline` + `flightNumber`, `origin`, `destination`; `legs[id].segments[].layover`. Self-transfer: `legs[].segments[].hasSelfTransfer` and `segmentFarings[].isSelfTransfer`. | `fareAmenities[]` with `CARRYON_BAG` and `CHECKED_BAG` and a `restriction` (`FEE`, `UNAVAILABLE`); `fees.checkedBagData`. Often `UNKNOWN`. | 3.0 to 4.1 MB for the last response; 5.3 to 5.9 MB per search. `searchStatus.passengerDetails` has an age (35). The tracking URLs have session ids. |
| **Google Flights** | `GET https://www.google.com/travel/flights/search?tfs=...`. The results are in the HTML of the page, in the inline script `AF_initDataCallback({key: 'ds:1', ...})`, only after a full load of the results page. A search on the page with no reload is not in the captures. Search 2 (Lisbon) failed: "Oops, something went wrong" (`ErrorResponse` code 13). | Positional arrays with no field names (for example `[null,null,null,"AMS",...,[9,40],...]`). Fragile, against P3. | Only local times as arrays (`[2026,12,1]`, `[9,40]`). The parser needs a table IATA code → time zone. | One price per itinerary. No currency field (the page shows £). No seller and no booking link in the results: Google loads the booking options only after a click. | Carrier and flight number at array positions (`["KL","1919",null,"KLM"]`). No self-transfer field found. | No baggage field found. | 43 KB. No personal data found, but a change of an array position changes the meaning of a value with no error. |
| **Skyscanner** | Blocked: the site answers each station lookup (`/g/autosuggest-search/api/v1/search-flight/...`) with status 403 (bot detection), so the form shows no stations and a search cannot start (#328). #442 asks for a second try by hand. | – | – | – | – | – | – |

## The choice and the reason

Kiwi.com is the flight source. Kayak is the second choice; Google Flights and Skyscanner are not possible now.

- **P1 (passive capture only).** Kiwi.com and Kayak are equal: the page sends the search request itself, and the
  userscript only reads the response. Google Flights puts the results in the HTML only at a page load. Skyscanner
  blocks the search.
- **P3 (robust sources first).** Kiwi.com gives UTC times for each segment, so the parser needs no airport table and
  cannot fail on an unknown airport. Its fields have names, and it marks a self-transfer and the baggage clearly
  (`rank:risk`, `rank:door`). Kayak needs a time zone table for all transfer airports, mixes ads into the results and
  sends 7 polls. Google Flights uses positional arrays, and its second search failed.
- **P5 (untrusted and private data).** A Kiwi.com response is 124 to 172 KB with no personal data. A Kayak response
  is up to 4.1 MB (25 times more) with an age and tracking URLs; that is more data to store and to trim.

Kiwi.com and Kayak are not equal (P3 and P5 favor Kiwi.com), so there is no decision ticket.

The known limits of Kiwi.com:
- A response has 10 itineraries (`limit` of the request). The captures do not show how the page loads more
  results; #332 must check it on the page.
- The currency comes from the request (`variables.options.currency`), not from the response.
- `priceEur.amount` is a conversion with 6 decimals: the parser uses `price.amount` and the request currency.

## The method for the next tickets

- **Response to intercept** (#332): `POST` to `api.skypicker.com/umbrella/v2/graphql` with
  `featureName=SearchOneWayItinerariesQuery` in the URL, on the pages of `www.kiwi.com`. Send each response (the
  page polls 3 or 4 times; the ingest upsert removes duplicates). Send the response body and the currency of the
  request as `raw`, for example `{"currency": "gbp", "response": <body>}`. Do not send `serverToken`,
  `searchSessionId` or other values of the request.
- **Time zone method** (#331): for each segment end, UTC = `utcTimeIso`, and the original offset =
  `localTime` − `utcTimeIso` (for example `06:35` local and `05:35Z` give `+01:00` at AMS). No airport table.
- **Fares** (#331): one fare per `bookingOptions.edges[].node`, with `itineraryProvider.code` as the fare name,
  `Decimal(price.amount)` and the request currency in upper case; `bookingUrl` with the prefix
  `https://www.kiwi.com` as the link.
- **Self-transfer** (#331): `pnrCount` > 1, or a segment with `guarantee` not null.
- **Fixtures** (#330): keep the fields of the parser only; remove `server`, `wishlistItineraryInfo`, `shareId`,
  `id`, the booking tokens in `bookingOptions.edges[].node.token`, and the token in `bookingUrl` if the size test
  needs it.
