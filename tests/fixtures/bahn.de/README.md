# bahn.de fixtures

Trimmed captures of `POST https://int.bahn.de/web/api/angebote/fahrplan` (the search results; the hook URL of the
userscript). Source: the HAR files of #61 (branch `owner/bahn-captures`). Each file has the request body, and the
response body with 3 connections of the original response. The files have no headers, no cookies and no personal data.

| File | Search | What it shows |
|---|---|---|
| `fahrplan-koeln-muenchen.json` | Köln Hbf → München, 2nd class, no discount | 1 transfer; one connection with no price (`angebotsPreis` absent); real-time `echtzeit` |
| `fahrplan-amsterdam-zuerich.json` | Amsterdam Centraal → Zürich | international, 1–3 transfers, one connection with no price |
| `fahrplan-amsterdam-bern-night.json` | Amsterdam Centraal → Bern, 20:48 | night connections that arrive on the next day |
| `fahrplan-koeln-muenchen-bahncard25.json` | Köln Hbf → München, BahnCard 25 2nd class | the discount in `reisende[].ermaessigungen`; one direct connection |

Notes for the parser:
- The times (`abfahrt.sollzeit`, `ankunft.sollzeit`, `echtzeit`) are local times with no offset. The
  parser must find the timezone of each station (not in these files).
- Each response has only one price per connection (`angebotsPreis`, `angebotsPreisKlasse`); `reiseAngebote` is
  empty. The capture has no response with all fare classes and no page of later connections.
- `verbindungReference` is the cursor for earlier and later connections.
