"""The parser of an oebbtickets.at search or fare response (tests/fixtures/oebbtickets.at/README.md).

- A fare response (`POST /api/offer/v6/offers`) is one connection with its `offerSections`. A Nightjet section gives
  one fare per tier (seat, couchette, sleeper): the cheapest compartment price of the tier. The price of the offer is
  the sum of the cheapest fare of each section (2nd class); the Nightjet section adds its tier.
- A search response (`POST /api/hafas/v4/timetable`) has `connections[]` with no price. A capture
  {"response": ..., "prices": {connection id: amount}} gives the price of each connection; a connection with no
  price is rejected.

The times are local with no offset: the UIC country code of the station `esn` gives the timezone (as bahn.de). The
currency is EUR. The parser sends no request (P1)."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.parsers import ParseResult
from app.parsers.bahn import station_tz
from app.schemas import LegIn, OfferIn, _short_reason

BOOKING_URL = "https://shop.oebbtickets.at/"
CURRENCY = "EUR"
# Nightjet accommodation type -> fare name; the order is the order of the fares
TIERS = {"SEAT": "Seat", "COUCHETTE": "Couchette", "BERTH": "Sleeper"}
BUS = {"Bus", "BUS", "ICB", "NJB", "WB"}


def money(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError("a price is not a number")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def local(value: str, esn: Any) -> datetime:
    t = datetime.fromisoformat(value)
    return t if t.tzinfo else t.replace(tzinfo=station_tz(esn))


def legs(conn: dict) -> list[LegIn]:
    out = []
    for s in conn["sections"]:
        if s.get("type", "journey") != "journey":
            continue
        cat = s.get("category") or {}
        out.append(LegIn(
            mode="bus" if cat.get("name") in BUS or cat.get("train") is False else "train",
            carrier=(cat.get("longName") or {}).get("en") or cat.get("name"),
            service_no=" ".join(x for x in (cat.get("name"), cat.get("number")) if x) or None,
            from_name=s["from"]["name"],
            to_name=s["to"]["name"],
            depart_at=local(s["from"]["departure"], s["from"].get("esn")),
            arrive_at=local(s["to"]["arrival"], s["to"].get("esn")),
        ))
    return out


def _flex(offer: dict) -> str | None:
    f = offer.get("flexibility")
    return (f.get("en") if isinstance(f, dict) else f) or None


def _second(section: dict) -> list[dict]:
    """The offers of the 2nd class of a section (else of its first class)."""
    classes = section["travelClasses"]
    tc = next((c for c in classes if str(c.get("class")) == "2"), classes[0])
    return tc["offers"]


def _tiers(section: dict) -> dict[str, tuple[Decimal, str | None]]:
    """{fare name: (cheapest price, flexibility)} of the Nightjet tiers of a section; {} for a section with no tiers."""
    kinds = {c["id"]: c.get("accommodationType") for c in (section.get("media") or {}).get("compartments") or []}
    best: dict[str, tuple[Decimal, str | None]] = {}
    for offer in _second(section):
        for c in (offer.get("reservation") or {}).get("compartments") or []:
            name = TIERS.get(kinds.get(c.get("id")))
            if name is None or c.get("price") is None:
                continue
            p = money(offer.get("price") or 0) + money(c["price"])
            if name not in best or p < best[name][0]:
                best[name] = (p, _flex(offer))
    return {n: best[n] for n in TIERS.values() if n in best}


class OebbParser:
    source = "oebbtickets.at"
    version = "1.0.0"
    hosts = ("shop.oebbtickets.at",)
    paths = ("/api/hafas/v4/timetable", "/api/offer/v1/prices", "/api/offer/v6/offers")

    def parse(self, raw: Any) -> ParseResult:
        """Offers of a capture {"response", "prices"} or of the response body only."""
        if not isinstance(raw, dict):
            raise ValueError("the oebbtickets.at payload is not an object")
        response = raw.get("response", raw)
        if not isinstance(response, dict):
            raise ValueError("the oebbtickets.at response is not an object")
        result = ParseResult()
        if "offerSections" in response:
            try:
                result.offers.extend(self._fares(response))
            except ValidationError as e:
                result.errors.append({"index": 0, "reason": _short_reason(e)})
            except (KeyError, TypeError, ValueError, AttributeError, IndexError, ArithmeticError) as e:
                result.errors.append({"index": 0, "reason": f"bad connection: {type(e).__name__} {e}"[:200]})
            return result
        conns = response.get("connections")
        if not isinstance(conns, list):
            raise ValueError("the oebbtickets.at payload has no connections list or offerSections")
        prices = raw.get("prices") if isinstance(raw.get("prices"), dict) else {}
        for i, conn in enumerate(conns):
            try:
                if conn.get("id") not in prices:
                    raise ValueError("no price")
                result.offers.append(OfferIn(
                    external_id=conn["id"][:200], price_amount=money(prices[conn["id"]]),
                    price_currency=CURRENCY, legs=legs(conn), booking_url=BOOKING_URL,
                ))
            except ValidationError as e:
                result.errors.append({"index": i, "reason": _short_reason(e)})
            except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError) as e:
                result.errors.append({"index": i, "reason": f"bad connection: {type(e).__name__} {e}"[:200]})
        return result

    def _fares(self, response: dict) -> list[OfferIn]:
        trip = legs(response["connection"])
        base, tiers = Decimal("0"), {}
        for section in response["offerSections"]:
            t = _tiers(section)
            if t and not tiers:
                tiers = t
                continue
            base += min(money(o["price"]) for o in _second(section))
        if not tiers:
            tiers = {None: (Decimal("0"), None)}
        return [
            OfferIn(price_amount=base + price, price_currency=CURRENCY, fare_name=name, flexibility=flex,
                    travel_class="standard", legs=trip, booking_url=BOOKING_URL)
            for name, (price, flex) in tiers.items()
        ]
