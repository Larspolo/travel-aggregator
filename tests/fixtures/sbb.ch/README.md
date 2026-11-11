# sbb.ch fixtures

Trimmed captures of the connection search of `https://www.sbb.ch` (`POST https://graphql.www.sbb.ch/`, GraphQL).
Source: the HAR file of #1776 (branch `owner/sbb-captures`, file `captures/sbb/1776-sbb-1776.har`). The capture date
is 2026-11-11.

Each file has `url`, `method`, `request` (only the method and the GraphQL `variables`: no query text, no headers, no
cookies) and `response` of the `Trips` query, and `prices`: the `TripPrices` query of the same trips in the same form.
The `notices`, `situations`, `serviceAlteration`, `occupancy` and accessibility keys are removed. The searches are
Basel SBB (`8500010`) → Zürich HB (`8503000`) for 1 adult; the prices are in CHF centimes.

| File | Search | What it shows |
|---|---|---|
| `search-basel-zuerich-half-fare.json` | Wed 2026-11-11, after 07:25, Half Fare card (`reductions: ["HALF_FARE"]`) | 4 trips: 07:33 (IC 3 561), 07:36 (IR 36 2061), 07:43 (IR 37 2261), 07:43 (IR 37 2261, then IC 5 511: 1 transfer). Saver prices (`NON_FLEXIBLE`). |
| `search-basel-zuerich.json` | Tue 2026-12-08, after 08:00, no card (`reductions: ["NONE"]`) | 5 trips: 08:07 (IC 3 763), 08:07 (IR 36 1963), 08:33 (IC 3 563), 08:43 (IR 37 2263), 08:43 (IR 37 2263, then IC 5 513). Flex prices (`FULL_FLEXIBLE`). |

Notes for the parser:

- A trip has `id` (about 1000 characters), `legs[]` (`PTRideLeg` with `start`, `end`, `departure.time`,
  `arrival.time` with an offset, and `serviceJourney.serviceProducts[0]` with `vehicleMode`,
  `vehicleSubModeShortName` and `number`) and `summary`. The payload names no operator.
- `prices.response.data.tripPrices[]` has `tripId` and `tripPrices[]` (`price.amount` in centimes, `price.currency`,
  `travelClass` `FIRST` or `SECOND`, `afterSaleFlexibility`).
