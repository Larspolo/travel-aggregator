# bahn.de fixtures

Trimmed captures of `POST https://int.bahn.de/web/api/angebote/fahrplan` (the search results; the hook URL of the
userscript). Source: the HAR files of #61 (branch `owner/bahn-captures`). Each file has the request body, and the
response body with 3 connections of the original response. The files have no headers, no cookies and no personal data.

| File | Search | What it shows |
|---|---|---|
| `fahrplan-koeln-muenchen.json` | Köln Hbf → München, 2nd class, no discount | 1 transfer; one connection with no price (`angebotsPreis` absent); real-time `echtzeit` |
| `fahrplan-amsterdam-zuerich.json` | Amsterdam Centraal → Zürich | international, 1–3 transfers, one connection with no price |
| `fahrplan-amsterdam-bern-night.json` | Amsterdam Centraal → Bern, 20:48 | night connections that arrive on the next day |
| `recon-169.json` | Köln Hbf → München, 2026-12-01 05:25 (`POST /web/api/angebote/recon`, HAR of #169; only the fields of the parser) | 12 `reiseAngebote`: each fare class in 1st and 2nd class, BahnCard trials (`Probe BahnCard 25/50`) and the prices with a trial card after them |
| `fahrplan-koeln-muenchen-bahncard25.json` | Köln Hbf → München, BahnCard 25 2nd class | the discount in `reisende[].ermaessigungen`; one direct connection |
| `fahrplan-amsterdam-berlin.json` | Amsterdam Centraal → Berlin Hbf, 2026-12-08 06:00, 2nd class, no discount (HAR of #482, branch `owner/merge-captures`; all 5 connections) | the same search as `search-amsterdam-berlin-pair.json` of nsinternational.com: the merge of two sources (#485) |
| `fahrplan-amsterdam-berlin-2-adults.json` | Amsterdam Centraal → Berlin Hbf, 2026-12-01 08:00, 2nd class, 2 adults (`reisende[].anzahl` 2; HAR of #762, branch `owner/travelers-captures`; 3 of 5 connections, only the fields of the parser) | the price of the group (#767): 113.98, 131.98 and 149.98 for 2 adults |

Notes for the parser:
- The times (`abfahrt.sollzeit`, `ankunft.sollzeit`, `echtzeit`) are local times with no offset. The
  parser must find the timezone of each station (not in these files).
- The recon response ("Weiter" on a connection) has one entry per fare in `reiseAngebote` (`name`, `klasse`,
  `kontextTyp`, `preis`). The parser keeps the first entry of each name and class and skips the `Probe` trials.
- Each fahrplan response has only one price per connection (`angebotsPreis`, `angebotsPreisKlasse`); `reiseAngebote` is
  empty. The capture has no response with all fare classes and no page of later connections.
- `verbindungReference` is the cursor for earlier and later connections.

The travelers (#767):
- `angebotsPreis.betrag` is the price for all travelers of `reisende`, not the price per person. Evidence: the capture
  of #762 for 2 adults has only prices that are 2 times a price that ends in .99 (113.98 = 2 × 56.99, 131.98 =
  2 × 65.99, 149.98 = 2 × 74.99), and ICE 143 + ICE 847 at 08:00 costs 113.98 on the same day for 2 adults on
  nsinternational.com (#763), where one admission has the total of both travelers. The 1-adult capture of the same
  connection (2026-12-08) costs 49.99. The connection has no price per person.
- The parser has `group_price = True`: the ranking divides the price by `Capture.travelers` and shows the price of the
  group in the breakdown (`app/ranking.py`, `for_group()`).
