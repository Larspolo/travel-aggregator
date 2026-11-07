"""The parser of a bahn.de fahrplan or recon payload (`POST /web/api/angebote/fahrplan` or `/recon`, tests/fixtures/bahn.de/README.md).

The payload has local times with no offset. The UIC country code (the first 2 digits of the station `extId`) gives the
timezone of each station; Europe/Berlin is the default. The parser sends no request (P1)."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.parsers import ParseResult
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


def discounts(request: dict | None) -> list[str]:
    out = []
    for r in (request or {}).get("reisende") or []:
        for e in r.get("ermaessigungen") or []:
            name = DISCOUNTS.get(e.get("art"))
            if name and name not in out:
                out.append(name)
    return out


class BahnParser:
    source = "bahn.de"
    version = "1.0.0"

    def parse(self, raw: Any) -> ParseResult:
        """Offers of a capture {"request", "response"} or of the response body only."""
        if not isinstance(raw, dict):
            raise ValueError("the bahn.de payload is not an object")
        response = raw.get("response", raw)
        request = raw.get("request") if "response" in raw else None
        conns = response.get("verbindungen") if isinstance(response, dict) else None
        if not isinstance(conns, list):
            raise ValueError("the bahn.de payload has no verbindungen list")
        extra = discounts(request)
        result = ParseResult()
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

    def _offers(self, conn: dict, extra: list[str]) -> list[OfferIn]:
        """One offer per fare class of `reiseAngebote` (the recon response), else the one `angebotsPreis` (#445)."""
        fares, seen = [], set()
        for a in conn.get("reiseAngebote") or []:
            name, klasse = (a.get("name") or "").strip(), a.get("klasse")
            # a BahnCard trial is no ticket, and the prices after it are the prices with that trial card
            if name.startswith("Probe ") or (name, klasse) in seen or (a.get("preis") or {}).get("betrag") is None:
                continue
            seen.add((name, klasse))
            fares.append((a["preis"], [name, CLASSES.get(klasse, "")]))
        if not fares:
            price = conn.get("angebotsPreis")
            if not price or price.get("betrag") is None:
                raise NoPrice("no price (angebotsPreis)")
            fares = [(price, [CLASSES.get(conn.get("angebotsPreisKlasse"), "")])]
        legs = []
        for a in conn["verbindungsAbschnitte"]:
            vm = a.get("verkehrsmittel") or {}
            if vm.get("typ") in SKIP_TYPES:
                continue
            attrs = {z.get("key"): z.get("value") for z in vm.get("zugattribute") or []}
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
            ))
        return [OfferIn(
            external_id=conn.get("tripId"),
            # str() first: a JSON float such as 130.99 must not become a long binary Decimal
            price_amount=Decimal(str(price["betrag"])).quantize(Decimal("0.01")),
            price_currency=price.get("waehrung") or "EUR",
            fare_name=", ".join(x for x in fare + extra if x) or None,
            legs=legs,
            booking_url=BOOKING_URL,
        ) for price, fare in fares]
