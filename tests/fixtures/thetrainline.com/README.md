# thetrainline.com fixtures

Trimmed captures of the search responses of `POST https://www.thetrainline.com/api/journey-search/` (the hook URL of
the userscript: the response of the journey search of the page). Source: the HAR files of #960 (branch
`owner/trainline-captures`, files `captures/thetrainline.com/960-trainline-960-1-london-edinburgh.har` and
`960-trainline-960-2-amsterdam-berlin.har`). The capture date is 2026-11-08.

Each file has `url`, `request` (only the method and the JSON body: no headers, no cookies) and `response` (the JSON
body: `data.journeySearch` and the lookup dicts of `data`). The searches are for Tue 2026-12-01, departing after 09:45,
for 1 adult. The prices are in GBP.

| File | Search (place codes of the request) | What it shows |
|---|---|---|
| `search-london-edinburgh.json` | London (`urn:trainline:generic:loc:182gb`) → Edinburgh (`urn:trainline:generic:loc:EDB9328gb`) | 3 journeys: 10:03 (LNER, direct), 10:15 (Lumo, direct), 10:33 (LNER, then CrossCountry from York: 1 transfer). Fare types such as `Advance Single` and `Advance Single (1st Class)`. `currencyConversionApplied` is `false`. |
| `search-amsterdam-berlin.json` | Amsterdam Centraal (`urn:trainline:generic:loc:5894`) → Berlin Hbf (`urn:trainline:generic:loc:7630`) | 3 journeys: 08:31 (ICE 225, then ICE 547: 1 transfer), 10:00 (ICE 145, direct), 10:31 (ICE 123, then ICE 549: 1 transfer). `currencyConversionApplied` is `true`. |

The 08:31 and 10:00 journeys of the Amsterdam search are also in `tests/fixtures/bahn.de/fahrplan-amsterdam-berlin-2-adults.json`
(the merge test of #980).

Notes for the parser:

- **Structure**: `data.journeySearch.journeys` is a dict of journeys by id. A journey names its `legs` and its
  `sections` by id. A section names its `alternatives` (one alternative per price). An alternative names its `fares`.
  A fare names its `fareType`, `origin`, `destination` and its `fareLegs` (each with a `travelClass`).
- **Lookups**: `journeySearch.legs`, `sections`, `alternatives`, `fares` and `journeySearch.passengers` are dicts by id.
  `data` has `locations`, `carriers`, `fareTypes`, `transportModes`, `passengerTypes` and the other lookup dicts. Only
  the ids that the kept objects name are in the file (see `tests/test_trainline_fixtures.py`).
- **Alternatives**: all alternatives of the kept journeys are in the file (126 in the London search, 18 in the
  Amsterdam search). The parser must choose between them.
- **Passengers**: every passenger id is `p1`. In the request, `passengers[].id` is removed. The site makes the age group
  into a `dateOfBirth` field (note of #960); its value is `REDACTED` in these files.

Removed to keep the file under 300 kB (the parser does not read them): in each alternative `selectedExtras`,
`availableExtras`, `upsellProposals`, `billableUnits` and `comfortClassCorrelationToken`; in each fare
`nonContractualTerms`, `deliveryOptions` and `permittedLocations`; in each fare type `conditions` and
`conditionsSummary`. The lookup entries that only these fields named are removed too.

Each file is under 300 kB. The files have no names, no e-mail addresses, no customer ids, no cookies and no tokens.
