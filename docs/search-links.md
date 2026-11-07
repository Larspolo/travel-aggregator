# Search URLs of the sites (`trip:links`)

The owner captured these URLs in a private window with no login (#316): Amsterdam → Berlin, one way,
1 December 2026, 1 adult. The app uses these forms to make search links from the values of a trip. P1: the app only
makes a link; the owner opens it.

## bahn.de

The search is in the `#` fragment, not in the query.

```
https://www.bahn.de/buchung/fahrplan/suche#sts=true&so=Amsterdam%20Centraal&zo=Berlin%20Hbf&kl=2&r=13:16:KLASSENLOS:1&soei=8400058&zoei=8011160&hd=2026-12-01T08:14:37&hza=D&ar=false&s=true&d=false
```

- Stations: `so`/`zo` (names), `soei`/`zoei` (EVA numbers). The full capture also has `soid`/`zoid` (HAFAS
  location IDs: `A=1@O=<name>@X=..@Y=..@U=80@L=<EVA>@...`).
- Date and time: `hd=YYYY-MM-DDTHH:MM:SS`. Class: `kl=2`. Travellers: `r=13:16:KLASSENLOS:1` (1 adult).

## NS International

```
https://www.nsinternational.com/en/traintickets-v3/#/search/NLASC/DEBHF/20261201?pax=A
```

- Stations: station codes in the fragment path (`NLASC` Amsterdam Centraal, `DEBHF` Berlin Hbf).
- Date: `YYYYMMDD`. Travellers: `pax=A` (1 adult).

## Flixbus

`www.flixbus.nl` redirects to `www.flixbus.co.uk`; the search opens on `shop.flixbus.co.uk`.

```
https://shop.flixbus.co.uk/search?departureCity=40dde3b8-8646-11e6-9066-549f350fcb0c&arrivalCity=40d8f682-8646-11e6-9066-549f350fcb0c&route=Amsterdam-Berlin&rideDate=01.12.2026&adult=1&_locale=en_GB&departureCountryCode=NL&arrivalCountryCode=DE
```

- Stations: `departureCity`/`arrivalCity` (city UUIDs; the same as `from_city_id`/`to_city_id` in the captures of
  #235).
- Date: `rideDate=DD.MM.YYYY`. Travellers: `adult=1`.
- The owner removed the tracking and session parameters (`atb_pdid`, `_sp`, `_spnuid`, P5) and the `features[...]`
  flags. Do not add them to a link.
