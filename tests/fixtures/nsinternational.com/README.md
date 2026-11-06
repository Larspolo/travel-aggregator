# nsinternational.com fixtures

Trimmed captures of `POST https://www.nsinternational.com/api/v2/sales/traveloffers/search?returnAdmissionPricing=true&filterOnCheapestOffer=false`
(the search results; the hook URL of the userscript). Source: the 3 HAR files of #122 (zip `ns-captures.zip` on branch
`owner/ns-captures`). Each file has the request body, and the response body with 3 connections of the original
response (`data.travelOffers`). The files have no headers, no cookies, no names, no e-mail addresses, no customer ids
and no tokens. The searches are for 2026-11-26.

| File | Search | What it shows |
|---|---|---|
| `search-amsterdam-london.json` | Amsterdam Centraal (NLASC) → London St. Pancras (GBSPX), 07:00 | a direct Eurostar (1 train leg, 0 changes); a connection with 2 changes and a `TRANSFER` leg; offers with 2 or 3 fare names |
| `search-amsterdam-berlin.json` | Amsterdam Centraal (NLASC) → Berlin Hbf (DEBHG) | 1 change with 2 train legs; 6 offers per connection; `nsiNumberOfChanges` is 0 while `numberOfChanges` is 1 |
| `search-rotterdam-paris.json` | Rotterdam Centraal (NLRTC) → Paris (FRPAR), 07:00 | direct connections (0 changes), 3 offers each; a fare name with a leading space |

Notes for the parser:

- **Request body** (`request`): `origin` and `destination` are station codes; `travelers[]` has only `ageType` (`A`);
  `outboundDatetime` has `datetime` (local time, no offset) and `timetype` (`DEPARTURE`).
- **Connections**: `response.data.travelOffers[]`. Each has `id`, `itinerary`, `offers[]` and `messages[]`. A
  connection can have 0 offers (`bookableStatus` is `NOT_BOOKABLE_NO_SERVICE`). Skip the price for such a connection.
- **Price**: `offers[].totalPrice.amount` (a JSON number, for example `107.99`: read it as a string and make a
  `Decimal`, never a `float`) and `offers[].totalPrice.currency` (`EUR`). `totalPriceWithOptionalAccommodations` is
  the price with the optional extras; the basic price is the one to rank. `offers[].admissions[].priceDetails.total`
  is the same amount for the traveler.
- **Fare name and class**: `offers[].name` (for example `Comfort Class`, `Second Class`, `Standard Premier`,
  `Business Premier`). `offers[].classLevel` is `"1"` or `"2"`. Trim the name: one capture has a leading space
  (`" Comfort"`).
- **Times**: `itinerary.origin.departure.plannedLocalDateTime` and `itinerary.destination.arrival.plannedLocalDateTime`
  are local times with no offset (for example `2026-11-26T06:38:00`). The station `timeZone` is a string of the form
  `GMT+01:00` (Amsterdam, Berlin, Paris) or `GMT` (London). The times are in standard time: both the Netherlands and the
  UK are on standard time in these captures. The parser must not assume a fixed offset for all dates.
  `delay` is an ISO duration (`PT0S`). The departure and arrival platforms are in `platform`; `updatedPlatform` is
  `null` in these captures.
- **Duration**: `itinerary.duration` is an ISO 8601 duration (`PT4H47M`).
- **Legs**: `itinerary.modalities[]` is the list of legs in order. A `TRAIN` leg has `code` (the product, for example
  `ICE`, `Eurostar`, `Eurocity Direct`), `name`, and `number` (the train number). A `TRANSFER` leg is a walk between
  two stations: its `code`, `name` and `number` are `null`. The London connection with 2 changes has the list
  `TRAIN, TRAIN, TRANSFER, TRAIN`.
- **Changes**: `itinerary.numberOfChanges` counts the changes between train legs (it is one less than the number of
  `TRAIN` legs). `itinerary.nsiNumberOfChanges` is a different NS count and is 0 in these captures: use
  `numberOfChanges` for the score.
- **Cursor**: `response.data.scroll` has `searchId`, `earlier` (`PREV_DEPARTURE`) and `later` (`NEXT_DEPARTURE`). The
  captures have no page of earlier or later connections.
- **Other fields**: `newOutboundTravelOfferId` and `newOutboundOfferId` are `null`. `messages` is empty in these
  captures.
