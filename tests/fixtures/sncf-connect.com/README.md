# sncf-connect.com fixtures

Trimmed captures of `POST https://www.sncf-connect.com/bff/api/v1/itineraries` (the search results; the path that
the userscript intercepts). Source: the HAR files of #956 (branch `owner/sncf-captures`, files
`captures/sncf-connect.com/956-sncf-956-1-paris-lyon.har` and `956-sncf-956-2-paris-marseille.har`). Captured on
2026-11-08.

Each file has `url`, `method`, `request` (only `schedule` and `mainJourney` of the request body) and `response`
(only `longDistance.proposals.proposals` and `longDistance.status`). The files have no cookies, no tokens, no
session, visitor or consent ids, no e-mail addresses and no passenger data.

The search in both files: Tue 2026-12-01 from 06:00, 1 adult, EUR.

| File | Search | What it shows |
|---|---|---|
| `search-paris-lyon.json` | Paris (Gare de Lyon) → Lyon | 2 direct TGV INOUI (first-class fares and second-class fares) and 1 direct TER (second class only) |
| `search-paris-marseille.json` | Paris (Gare de Lyon) → Marseille | 1 connection with 1 change (`1 correspondance`, 2 `train` steps and a `connection` step), 1 direct OUIGO (second class only), 1 direct TGV INOUI |

Notes for the parser:

- **Endpoint**: `POST /bff/api/v1/itineraries`. The body has `schedule.outward.date` (UTC, `2026-12-01T06:00:00.000Z`),
  and `mainJourney.origin` and `mainJourney.destination` (`label` and `id`). The response has `longDistance.status`
  (`RESULTS`) and the list `longDistance.proposals.proposals`.
- **Times**: the times are only `timeLabel` strings of the local time of France (`"06:20"`). The response has no
  offset. Store UTC and the offset of Europe/Paris for the date in the next note.
- **Date**: the date is in `tripIv.vehicleDetails.request.date` of each `train` step (`2026-12-01`), and at the start
  of `travelId` (`2026-12-01T06:20_6641`).
- **Price**: only `priceLabel` in French form (`"55 €"`, with a no-break space before the euro sign; `"65,60 €"` with a
  comma for the cents). Read it as a string and make a `Decimal`, never a `float`.
- **Comfort class**: `firstComfortClassOffers` and `secondComfortClassOffers`. Each is a group with `title` and
  `offers[]`. Each offer has `comfortClass.code` (`FIRST` or `SECOND`), `priceLabel` and `travelersFares[]`. Each fare
  has `segmentFares[]` with the fare name (`fareName`) and the train number (`transporterDescription`, for example
  `"6641"`).
- **Train kind**: `transporter.description` of each `train` step (`TGV INOUI`, `OUIGO`, `Train TER`). The proposal
  has the same text in `transporterDescription`.
- **Transfer**: a proposal with `durationLabel` and `transporterDescription` `1 correspondance` has 2 `train` steps and
  1 `connection` step in `globalTimeline.steps`. The `connection` step has `correspondanceTimeLabel` (`"10 min"`).
  The number of changes is the number of `train` steps minus 1.
- **Duration**: `durationLabel` is a short text (`2h02`, `3h46`).
- **Status**: `status` of each proposal is `{"isBookable": true}` in these captures. Skip the proposals that are not
  bookable.
- **Stations**: `departure` and `arrival` have `originStationLabel` and `destinationStationLabel` (for example
  `Paris - Gare De Lyon - Hall 1 & 2`, `Lyon Part Dieu`, `Marseille Saint-Charles`), and `timeLabel`. The OUIGO
  starts at `Marne-La-Vallee - Chessy`.
