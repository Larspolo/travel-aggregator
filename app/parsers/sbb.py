"""The parser of an SBB connection search (`POST https://graphql.www.sbb.ch/`, tests/fixtures/sbb.ch/README.md).

A capture is the `Trips` query {"url", "method", "request", "response"} with the `TripPrices` query of the same
connections in `prices`. One offer per trip and price of `tripPrices`. The amounts are in centimes. The times have the
offset of the payload. The parser sends no request (P1)."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.parsers import ParseResult, count
from app.schemas import LegIn, OfferIn, _short_reason

BOOKING_URL = "https://www.sbb.ch/"
MODES = {"TRAIN": "train", "BUS": "bus", "SHIP": "ferry"}  # TRAMWAY, CABLEWAY and the rest are "other"
CLASSES = {"FIRST": ("first", "1st class"), "SECOND": ("standard", "2nd class")}
FLEX = {"NON_FLEXIBLE": "Saver", "FULL_FLEXIBLE": "Flex"}
CARDS = {"HALF_FARE": "Half Fare card", "GA": "GA travelcard"}


def aware(value: str) -> datetime:
    t = datetime.fromisoformat(value)
    if t.tzinfo is None:
        raise ValueError(f"a time with no offset: {value}")
    return t


def service_no(product: dict) -> str | None:
    """The form of bahn.de ("IC 561", not "IC 3 561"), so that the fingerprint matches the other sources (#481)."""
    kind, number = product.get("vehicleSubModeShortName"), product.get("number")
    if kind and number:
        return f"{kind} {number}"
    return product.get("name") or None


def discounts(passengers: Any) -> list[str] | None:
    """The card names of the `reductions` of the request (#1752); None when the request has no passengers list."""
    if not isinstance(passengers, list):
        return None
    out: list[str] = []
    for p in passengers:
        for r in (p.get("reductions") if isinstance(p, dict) else None) or []:
            name = CARDS.get(r, r if isinstance(r, str) and r not in ("NONE", "") else None)
            if name and name not in out:
                out.append(name)
    return out


def variables(part: Any) -> dict:
    req = part.get("request") if isinstance(part, dict) else None
    body = req.get("body") if isinstance(req, dict) else None
    v = body.get("variables") if isinstance(body, dict) else None
    v = v.get("input") if isinstance(v, dict) else None
    return v if isinstance(v, dict) else {}


class SbbParser:
    source = "sbb.ch"
    version = "1.0.0"
    redact_keys: frozenset[str] = frozenset()
    url_keep: frozenset[str] = frozenset()
    # the userscript of sbb.ch gives the hook URL (#1776); no HAR entry is read before then
    hosts: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()

    def parse(self, raw: Any) -> ParseResult:
        """Offers of a capture {"url", "request", "response", "prices"}; a capture with no prices gives no offer."""
        if not isinstance(raw, dict):
            raise ValueError("the sbb.ch payload is not an object")
        response = raw.get("response", raw)
        data = response.get("data") if isinstance(response, dict) else None
        trips = data.get("trips") if isinstance(data, dict) else None
        trips = trips.get("trips") if isinstance(trips, dict) else None
        if not isinstance(trips, list):
            raise ValueError("the sbb.ch payload has no data.trips.trips list")
        if not trips:
            raise ValueError("the sbb.ch payload has no connections")
        prices = raw.get("prices")
        pdata = (prices.get("response") or {}).get("data") if isinstance(prices, dict) else None
        plist = pdata.get("tripPrices") if isinstance(pdata, dict) else None
        by_id = {p["tripId"]: p for p in plist or [] if isinstance(p, dict) and isinstance(p.get("tripId"), str)}
        people = variables(prices).get("passengers")
        result = ParseResult(travelers=count(len(people)) if isinstance(people, list) else None,
                             discounts=discounts(people))
        for i, trip in enumerate(trips):
            try:
                if trip.get("id") not in by_id:
                    raise ValueError("no price")
                result.offers.extend(self._offers(trip, by_id[trip["id"]]))
            except ValidationError as e:
                result.errors.append({"index": i, "reason": _short_reason(e)})
            except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError) as e:
                result.errors.append({"index": i, "reason": f"bad trip: {type(e).__name__} {e}"[:200]})
        return result

    def _offers(self, trip: dict, price: dict) -> list[OfferIn]:
        legs = []
        for leg in trip["legs"]:
            if leg.get("__typename") != "PTRideLeg":
                continue  # a walk between two stops is no leg
            product = (leg.get("serviceJourney") or {}).get("serviceProducts", [{}])[0]
            legs.append(LegIn(
                mode=MODES.get(product.get("vehicleMode"), "other"),
                carrier=product.get("operator") or None,
                service_no=service_no(product),
                from_name=leg["start"]["name"], from_code=leg["start"].get("id"),
                to_name=leg["end"]["name"], to_code=leg["end"].get("id"),
                depart_at=aware(leg["departure"]["time"]), arrive_at=aware(leg["arrival"]["time"]),
            ))
        # the trip id is about 1000 characters: the departure and the services identify the trip
        ext = "|".join([legs[0].depart_at.isoformat(), *(x.service_no or "" for x in legs)])[:200] if legs else None
        offers = []
        for p in price["tripPrices"]:
            cls, cls_name = CLASSES[p["travelClass"]]
            flex = FLEX.get(p.get("afterSaleFlexibility"))
            amount = (Decimal(int(p["price"]["amount"])) / 100).quantize(Decimal("0.01"))
            offers.append(OfferIn(
                external_id=ext, price_amount=amount, price_currency=p["price"]["currency"],
                fare_name=", ".join(x for x in [flex, cls_name] if x), flexibility=flex, travel_class=cls,
                legs=legs, booking_url=BOOKING_URL,
            ))
        return offers
