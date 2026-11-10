"""The parser of a Eurostar journey search response (GraphQL `NewBookingSearch`, tests/fixtures/eurostar.com/README.md).

One offer per journey of `data.journeySearch.outbound.journeys` and class of service. The legs come from the first fare
of the journey (all fares have the same legs). The times are local station times with no offset: the timezone comes
from the UIC country code of the station (`station_tz`). The `isoDate` ends in `Z` but is a local time: not used.
A fare with no `displayPrice` or with 0 seats is sold out and is skipped. The parser sends no request (P1)."""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.parsers import ParseResult, count, seats
from app.parsers.bahn import station_tz
from app.schemas import LegIn, OfferIn, _short_reason

BOOKING_URL = "https://www.eurostar.com/"
CLASSES = {"STANDARD": "standard", "PLUS": "standard", "PREMIER": "first"}


def local(date: str, hhmm: str, uic: Any) -> datetime:
    return datetime.fromisoformat(f"{date}T{hhmm}").replace(tzinfo=station_tz(uic))


def money(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
        raise ValueError(f"a bad price: {value!r}")
    # str() first: a JSON float must not become a long binary Decimal
    return Decimal(str(value)).quantize(Decimal("0.01"))


class EurostarParser:
    source = "eurostar.com"
    version = "1.1.0"
    hosts = ("site-api.eurostar.com",)
    paths = ("/gateway",)

    @staticmethod
    def har_raw(url, method, request, response):
        """The raw form of the userscript: the operation and its variables, not the query text; None for other operations."""
        if not isinstance(request, dict) or request.get("operationName") != "NewBookingSearch":
            return None
        body = {"operationName": request["operationName"], "variables": request.get("variables")}
        return {"url": url, "method": method, "request": {"method": method, "body": body}, "response": response}

    def parse(self, raw: Any) -> ParseResult:
        """Offers of a capture {"url", "request", "response"}, of the response body only, or of its JSON text."""
        if isinstance(raw, (str, bytes)):
            raw = json.loads(raw, parse_float=Decimal)
        if not isinstance(raw, dict):
            raise ValueError("the eurostar.com payload is not an object")
        response = raw.get("response", raw)
        data = response.get("data") if isinstance(response, dict) else None
        search = data.get("journeySearch") if isinstance(data, dict) else None
        outbound = search.get("outbound") if isinstance(search, dict) else None
        journeys = outbound.get("journeys") if isinstance(outbound, dict) else None
        if not isinstance(journeys, list):
            raise ValueError("the eurostar.com payload has no data.journeySearch.outbound.journeys list")
        request = raw.get("request") if "response" in raw else None
        body = request.get("body") if isinstance(request, dict) else None
        variables = body.get("variables") if isinstance(body, dict) else None
        variables = variables if isinstance(variables, dict) else {}
        currency = variables.get("currency") if isinstance(variables.get("currency"), str) else "GBP"
        result = ParseResult(travelers=count(variables.get("adult")) if variables else None)
        for i, journey in enumerate(journeys):
            try:
                result.offers.extend(self._offers(journey, currency))
            except ValidationError as e:
                result.errors.append({"index": i, "reason": _short_reason(e)})
            except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError, IndexError) as e:
                result.errors.append({"index": i, "reason": f"bad journey: {type(e).__name__} {e}"[:200]})
        return result

    def _offers(self, journey: dict, currency: str) -> list[OfferIn]:
        fares = journey["fares"]
        legs = []
        for leg in fares[0]["legs"]:
            o, d, t = leg["origin"], leg["destination"], leg["timing"]
            legs.append(LegIn(
                mode="train",
                carrier=(leg.get("serviceType") or {}).get("name"),
                service_no=leg.get("serviceName"),
                from_name=o["name"],
                from_code=None,
                to_name=d["name"],
                to_code=None,
                depart_at=local(t["departureDate"], t["departureTime"], o["uic"]),
                arrive_at=local(t["arrivalDate"], t["arrivalTime"], d["uic"]),
            ))
        if not legs:
            raise ValueError("a journey with no legs")
        numbers = "-".join(leg.service_no or "" for leg in legs)
        offers = []
        for fare in fares:
            price = (fare.get("prices") or {}).get("displayPrice")
            if price is None or fare.get("seats") == 0:
                continue
            cos = fare["classOfService"]
            offers.append(OfferIn(
                external_id=f"{legs[0].depart_at.isoformat()} {numbers}",
                price_amount=money(price),
                price_currency=currency,
                fare_name=cos["name"],
                travel_class=CLASSES.get(cos.get("code")),
                seats_left=seats(fare.get("seats")),
                legs=legs,
                booking_url=BOOKING_URL,
            ))
        return offers
