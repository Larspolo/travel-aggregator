"""The parser of a bahn.de fahrplan or recon payload (`POST /web/api/angebote/fahrplan` or `/recon`, or of a day price payload
(`POST /web/api/angebote/tagesbestpreis`, "Bestpreise anzeigen"; tests/fixtures/bahn.de/README.md).

The payload has local times with no offset. The UIC country code (the first 2 digits of the station `extId`) gives the
timezone of each station; Europe/Berlin is the default. The parser sends no request (P1)."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.parsers import DayPrice, ParseResult, count
from app.schemas import LegIn, OfferIn, _short_reason

DEFAULT_TZ = "Europe/Berlin"
# UIC country code -> timezone
COUNTRY_TZ = {
    "80": "Europe/Berlin", "81": "Europe/Vienna", "84": "Europe/Amsterdam", "85": "Europe/Zurich",
    "87": "Europe/Paris", "88": "Europe/Brussels", "82": "Europe/Luxembourg", "83": "Europe/Rome",
    "86": "Europe/Copenhagen", "74": "Europe/Stockholm", "76": "Europe/Oslo", "51": "Europe/Warsaw",
    "54": "Europe/Prague", "55": "Europe/Budapest", "70": "Europe/London", "71": "Europe/Madrid",
}
# legs that are no vehicle: they are not a leg and not a transfer
SKIP_TYPES = {"WALK", "TRANSFER"}
MODES = {"BUS": "bus", "SCHIFF": "ferry"}
CLASSES = {"KLASSE_1": "1st class", "KLASSE_2": "2nd class"}
TRAVEL_CLASSES = {"KLASSE_1": "first", "KLASSE_2": "standard"}
DISCOUNTS = {"BAHNCARD25": "BahnCard 25", "BAHNCARD50": "BahnCard 50", "BAHNCARD100": "BahnCard 100"}
BOOKING_URL = "https://www.bahn.de/buchung/fahrplan/suche"


class NoPrice(ValueError):
    pass


def station_tz(ext_id: Any) -> ZoneInfo:
    return ZoneInfo(COUNTRY_TZ.get(str(ext_id or "")[:2], DEFAULT_TZ))


def local_time(t: dict, ext_id: Any) -> datetime:
    """The real-time value when there is one (a delayed train must stay after the leg before it), else the plan."""
    value = t.get("echtzeit") or t["sollzeit"]
    naive = datetime.fromisoformat(value)
    if naive.tzinfo is not None:
        return naive
    return naive.replace(tzinfo=station_tz(ext_id))


def discounts(request: dict | None) -> list[str] | None:
    """The discount cards of the travelers (#1750); None when the request has no reisende list."""
    if not isinstance(request, dict) or not isinstance(request.get("reisende"), list):
        return None
    return _cards(request)


def _cards(request: dict | None) -> list[str]:
    out = []
    for r in (request or {}).get("reisende") or []:
        for e in r.get("ermaessigungen") or []:
            name = DISCOUNTS.get(e.get("art"))
            if name and name not in out:
                out.append(name)
    return out


def travelers(request: dict | None) -> int | None:
    """The sum of `anzahl` of `request.reisende` (#764); None when the payload has no request."""
    if not isinstance(request, dict) or not isinstance(request.get("reisende"), list):
        return None
    try:
        return count(sum(int(r.get("anzahl") or 0) for r in request["reisende"]))
    except (TypeError, ValueError, AttributeError):
        return None


class BahnParser:
    source = "bahn.de"
    version = "1.3.0"
    # no personal key beyond PERSONAL_KEYS: the fixtures have no BahnCard number and no traveler name (#1903)
    redact_keys: frozenset[str] = frozenset()
    # the station codes and the date of the search are in the body, not in a URL: no query name to keep (#1903)
    url_keep: frozenset[str] = frozenset()
    hosts = ("www.bahn.de", "int.bahn.de")
    paths = ("/web/api/angebote/fahrplan", "/web/api/angebote/recon", "/web/api/angebote/tagesbestpreis")
    group_price = True  # the price is for all travelers of the request (#767; the fixture README)

    def parse(self, raw: Any) -> ParseResult:
        """Offers (or day prices, #1196) of a capture {"request", "response"} or of the response body only."""
        if not isinstance(raw, dict):
            raise ValueError("the bahn.de payload is not an object")
        response = raw.get("response", raw)
        request = raw.get("request") if "response" in raw else None
        if isinstance(response, dict) and isinstance(response.get("intervalle"), list):
            return self._day_prices(response["intervalle"], travelers(request))
        conns = response.get("verbindungen") if isinstance(response, dict) else None
        if not isinstance(conns, list):
            raise ValueError("the bahn.de payload has no verbindungen list")
        extra = _cards(request)
        result = ParseResult(travelers=travelers(request), discounts=discounts(request))
        for i, conn in enumerate(conns):
            try:
                result.offers.extend(self._offers(conn, extra))
            except NoPrice as e:
                result.errors.append({"index": i, "reason": str(e)})
            except ValidationError as e:
                result.errors.append({"index": i, "reason": _short_reason(e)})
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                result.errors.append({"index": i, "reason": f"bad connection: {type(e).__name__} {e}"[:200]})
        return result

    def _day_prices(self, intervals: list, people: int | None) -> ParseResult:
        """The cheapest price of each local day of the time intervals (`ab`, `preis`); a bad interval goes to `errors`."""
        result, best = ParseResult(travelers=people), {}
        for i, iv in enumerate(intervals):
            try:
                price = iv.get("preis") or {}
                if not iv.get("ab"):
                    raise NoPrice("no date (ab)")
                if price.get("betrag") is None:
                    raise NoPrice("no price (preis)")
                day = datetime.fromisoformat(iv["ab"]).date()
                # str() first: a JSON float such as 49.99 must not become a long binary Decimal
                amount = Decimal(str(price["betrag"])).quantize(Decimal("0.01"))
                if not amount.is_finite() or amount < 0:
                    raise NoPrice(f"bad price {price['betrag']!r}"[:200])
                currency = price.get("waehrung") or "EUR"
                if day not in best or amount < best[day].price_amount:
                    best[day] = DayPrice(day=day, price_amount=amount, price_currency=currency)
            except NoPrice as e:
                result.errors.append({"index": i, "reason": str(e)})
            except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError) as e:
                result.errors.append({"index": i, "reason": f"bad interval: {type(e).__name__} {e}"[:200]})
        result.day_prices = [best[d] for d in sorted(best)]
        return result

    def _offers(self, conn: dict, extra: list[str]) -> list[OfferIn]:
        """One offer per fare class of `reiseAngebote` (the recon response), else the one `angebotsPreis` (#445)."""
        fares, seen = [], set()
        for a in conn.get("reiseAngebote") or []:
            name, klasse = (a.get("name") or "").strip(), a.get("klasse")
            # a BahnCard trial is no ticket, and the prices after it are the prices with that trial card
            if name.startswith("Probe ") or (name, klasse) in seen or (a.get("preis") or {}).get("betrag") is None:
                continue
            seen.add((name, klasse))
            fares.append((a["preis"], [name, CLASSES.get(klasse, "")], klasse))
        if not fares:
            price = conn.get("angebotsPreis")
            if not price or price.get("betrag") is None:
                raise NoPrice("no price (angebotsPreis)")
            klasse = conn.get("angebotsPreisKlasse")
            fares = [(price, [CLASSES.get(klasse, "")], klasse)]
        legs = []
        for a in conn["verbindungsAbschnitte"]:
            vm = a.get("verkehrsmittel") or {}
            if vm.get("typ") in SKIP_TYPES:
                continue
            attrs = {z.get("key"): z.get("value") for z in vm.get("zugattribute") or []}
            # RP: a mandatory reservation; GP: the price includes it (#1621). RE alone is only a recommendation.
            reservation = None
            if "RP" in attrs:
                reservation = "included" if "GP" in attrs else "required"
            legs.append(LegIn(
                mode=MODES.get(vm.get("produktGattung"), "train"),
                carrier=attrs.get("BEF"),
                service_no=vm.get("name"),
                from_name=a["abfahrtsOrt"],
                from_code=a.get("abfahrtsOrtExtId"),
                to_name=a["ankunftsOrt"],
                to_code=a.get("ankunftsOrtExtId"),
                depart_at=local_time(a["abfahrt"], a.get("abfahrtsOrtExtId")),
                arrive_at=local_time(a["ankunft"], a.get("ankunftsOrtExtId")),
                reservation=reservation,
            ))
        return [OfferIn(
            external_id=conn.get("tripId"),
            # str() first: a JSON float such as 130.99 must not become a long binary Decimal
            price_amount=Decimal(str(price["betrag"])).quantize(Decimal("0.01")),
            price_currency=price.get("waehrung") or "EUR",
            fare_name=", ".join(x for x in fare + extra if x) or None,
            legs=legs,
            booking_url=BOOKING_URL,
            travel_class=TRAVEL_CLASSES.get(klasse),
        ) for price, fare, klasse in fares]
