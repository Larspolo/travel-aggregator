# kiwi.com fixtures

Trimmed captures of `POST https://api.skypicker.com/umbrella/v2/graphql?featureName=SearchOneWayItinerariesQuery`
(the search results of Kiwi.com; the hook URL of the userscript). Source: the HAR files of #328 (branch
`owner/flight-captures`, `captures/kiwi/`). Each search is one way, 1 December 2026, 1 adult, economy, currency GBP.

Each file has the currency of the request (`currency`) and the response body (`response`) with 3 itineraries of
the original response (`data.onewayItineraries.itineraries`). The last response of each capture is used: the one
with `hasMorePending` false.

| File | Search | What it shows |
|---|---|---|
| `search-amsterdam-zurich.json` | Amsterdam → Zürich | a direct flight with 2 fares (`KIWI`, `KIWI-BASIC`); a flight with a transfer in Paris (1 PNR); a direct flight with 1 fare |
| `return-amsterdam-lisbon.json` | Amsterdam → Lisbon, return (1 to 8 December 2026; HAR of #1004, the last `SearchReturnItinerariesQuery` response) | `data.returnItineraries`: 3 direct return itineraries (`outbound` and `inbound` in place of `sector`), 5 fares; the price is of the return ticket |
| `search-amsterdam-lisbon.json` | Amsterdam → Lisbon | a direct flight with 2 fares; a flight with a transfer in Madrid (1 PNR); a self-transfer (`pnrCount` 2, the second segment has a `guarantee`) |

Notes for the parser:
- The times are in UTC (`utcTimeIso`) and in local time (`localTime`, no offset). The offset is `localTime` minus `utcTimeIso`.
- The currency is `currency` of the file, not a field of the response. `price.amount` is a string: read it as a `Decimal`.
- `bookingOptions.edges[].node.bookingUrl` is relative to `https://www.kiwi.com`. The value of `token` is replaced with `REDACTED`.
- The files have no cookies, no session values, no passenger names and no e-mail addresses. The request values
  `serverToken` and `searchSessionId` are not in the files.
- `server`, `wishlistItineraryInfo`, `shareId`, `id` and the booking token of each fare are removed (they are not
  read by the parser, P5).
