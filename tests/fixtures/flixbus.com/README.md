# flixbus.com fixtures

Trimmed captures of `GET https://global.api.flixbus.com/search/service/v4/search` with the query parameters of the
search (the search results; the hook URL of the userscript). Source: the HAR files of #235 (branch
`owner/flixbus-captures`, files `captures/flixbus/235-flixbus-235.har` and `235-flixbus-235b.har`). Each file has
`url`, `request` (only the method: no headers, no cookies) and `response` (the JSON body with at most 3 connections:
2 direct and 1 with a transfer, when the capture has them). The files have no names, no e-mail addresses, no customer
ids and no tokens. The searches are for 2026-12-01, in GBP, for 1 adult.

| File | Search | What it shows |
|---|---|---|
| `search-amsterdam-paris.json` | Amsterdam Central → Paris (`search_by=cities`) | 2 direct connections and 1 connection with 1 change (bus, then bus the next day); a `direct express` product |
| `search-amsterdam-berlin.json` | Amsterdam Central → Berlin | 2 direct connections and 1 connection with 1 change (bus, then train); `transfer_type_key` `direct#train` |
| `search-utrecht-berlin.json` | Utrecht → Berlin (2026-12-01) | 2 direct connections and 1 connection with 1 change (bus, then bus); `transfer_type_key` `direct#fast` |

Utrecht → Berlin is the third search (bus, then bus).

Notes for the parser:

- **Hook URL and method**: `GET https://global.api.flixbus.com/search/service/v4/search`. The query has `from_city_id`,
  `to_city_id` (UUIDs), `departure_date` (`dd.mm.yyyy`), `products` (JSON, `{"adult":1}`), `currency` (`GBP`),
  `locale`, `search_by` (`cities`) and some flags. The request has no body.
- **Connections**: `response.trips[]`. Each trip has `departure_city_id`, `arrival_city_id`, `date` and `results`.
  `results` is a dict keyed by the connection `uid`; each value is one connection. Use the values, not the keys.
- **Status**: `results[].status` is `available` in these captures. Skip any other status.
- **Price**: `results[].price.total` (a JSON number, for example `25.48`: read it as a string and make a `Decimal`,
  never a `float`) and `price.original`, `price.average`. `price.total_with_platform_fee` (for example `26.48`) is the
  price with the platform fee. The fee is `1.00` in these captures. Currency: the `currency` query parameter (`GBP`);
  the response has no currency field.
- **Fare name**: there is no fare name field in these captures. The closest fields are `transfer_type` (`Direct`,
  `Direct express`, `Transfer`) and `transfer_type_key` (`direct`, `direct_express`, `direct#train`, `direct#express`,
  `direct#direct`). The `provider` field is `flixbus` for all connections.
- **Times**: `departure.date` and `arrival.date` are ISO 8601 with an offset of the local city time, for example
  `2026-12-01T01:10:00+01:00`. Parse them as timezone-aware values: store UTC and the original offset. The `date` of the
  trip is `2026-12-01T00:00:00+01:00` (the day of the search). `duration` is an object: `{"hours": 10, "minutes": 14}`.
- **Stations and cities**: `departure.station_id` and `arrival.station_id` are keys of `response.stations`. `city_id`
  is a key of `response.cities` (`name`, `slug`). `response.stations` has `name`, `is_train` and `importance`.
- **Legs**: `results[].legs[]` is the list of legs in order. Each leg has `ride_id`, `departure` and `arrival` (each
  with `date`, `city_id` and `station_id`), `means_of_transport` (`bus` or `train`), `operator_id` (key of
  `response.operators`), `brand_id` (key of `response.brands`), `amenities` and `seat_types`.
- **Transfer**: a connection with `len(legs) > 1` has a transfer. `transfer_type` is `Transfer`. The first leg ends at the
  station where the second leg starts. `messages[]` has the text for the traveller (for example: follow the signs to the
  train station). `intermediate_stations_count` is `0` on the direct connections and absent on the transfer connections: derive the
  number of changes from the legs (`len(legs) - 1`).
- **Seats and bikes**: `remaining.seats` and `available.seats` are `null` or a number. `remaining.capacity` is `high` in
  these captures. `available.bike_slots` is 0.
- **Other fields**: `response_uuid` is the id of the search response. `platform_fee_in_price_required` is `true`.
  `restrictions.sale_restriction` is `false` in these captures.
