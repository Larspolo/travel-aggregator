"""The parser of a Trainline journey search response (`POST /api/journey-search/`, tests/fixtures/thetrainline.com/README.md).

One offer per journey of `data.journeySearch.journeys` and fare name. Each alternative of the sections of a journey is
a price for the whole journey; many alternatives have the same fare name, so the parser keeps the cheapest one per
fare name (`upsert_offers` matches a fare by itinerary, source and fare name). The times have the offset of the local
station time. The parser sends no request (P1)."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.parsers import ParseResult, count
from app.schemas import LegIn, OfferIn, _short_reason

BOOKING_URL = "https://www.thetrainline.com/"
CLASS_WORDS = ("first", "1st", "standard", "2nd", "second")


def aware(value: str) -> datetime:
    t = datetime.fromisoformat(value)
    if t.tzinfo is None:
        raise ValueError(f"a time with no offset: {value}")
    return t


def travel_class(name: str) -> str | None:
    n = name.lower()
    if "first" in n or "1st" in n:
        return "first"
    if "standard" in n or "2nd" in n or "second" in n:
        return "standard"
    return None


def fare_name(type_name: str, class_name: str) -> str:
    """The fare type name, plus the class name when the fare type name does not say the class."""
    if not class_name or any(w in type_name.lower() for w in CLASS_WORDS):
        return type_name
    return f"{type_name}, {class_name}"


class TrainlineParser:
    source = "thetrainline.com"
    version = "1.1.0"
    hosts = ("www.thetrainline.com",)
    paths = ("/api/journey-search/",)

    @staticmethod
    def har_raw(url, method, request, response):
        """The raw form of the userscript: the request body with no date of birth (P5)."""
        body = dict(request) if isinstance(request, dict) else None
        if body and isinstance(body.get("passengers"), list):
            body["passengers"] = [{k: v for k, v in p.items() if k != "dateOfBirth"} if isinstance(p, dict) else p
                                  for p in body["passengers"]]
        return {"url": url, "method": method, "request": body and {"method": method, "body": body}, "response": response}

    def parse(self, raw: Any) -> ParseResult:
        """Offers of a capture {"url", "request", "response"} or of the response body only."""
        if not isinstance(raw, dict):
            raise ValueError("the thetrainline.com payload is not an object")
        response = raw.get("response", raw)
        data = response.get("data") if isinstance(response, dict) else None
        search = data.get("journeySearch") if isinstance(data, dict) else None
        journeys = search.get("journeys") if isinstance(search, dict) else None
        if not isinstance(journeys, dict):
            raise ValueError("the thetrainline.com payload has no data.journeySearch.journeys dict")
        request = raw.get("request") if "response" in raw else None
        body = request.get("body") if isinstance(request, dict) else None
        people = body.get("passengers") if isinstance(body, dict) else None
        result = ParseResult(travelers=count(len(people)) if isinstance(people, list) else None)
        for i, journey in enumerate(journeys.values()):
            try:
                result.offers.extend(self._offers(journey, data, search))
            except ValidationError as e:
                result.errors.append({"index": i, "reason": _short_reason(e)})
            except (KeyError, TypeError, ValueError, AttributeError, ArithmeticError) as e:
                result.errors.append({"index": i, "reason": f"bad journey: {type(e).__name__} {e}"[:200]})
        return result

    def _offers(self, journey: dict, data: dict, search: dict) -> list[OfferIn]:
        locations, carriers, modes = data["locations"], data.get("carriers") or {}, data.get("transportModes") or {}
        legs = []
        for leg_id in journey["legs"]:
            leg = search["legs"][leg_id]
            designation, number = leg.get("transportDesignation"), leg.get("timetableId")
            dep, arr = locations[leg["departureLocation"]], locations[leg["arrivalLocation"]]
            mode = (modes.get(leg.get("transportMode")) or {}).get("mode")
            legs.append(LegIn(
                mode="bus" if mode == "bus" else "train",
                carrier=(carriers.get(leg.get("carrier")) or {}).get("name"),
                # the form of bahn.de ("ICE 225"), so that the fingerprint gives the same itinerary (#481)
                service_no=" ".join(x for x in [designation, number] if x) if designation else None,
                from_name=dep["name"],
                from_code=None,
                to_name=arr["name"],
                to_code=None,
                depart_at=aware(leg["departAt"]),
                arrive_at=aware(leg["arriveAt"]),
                # Trainline books the mandatory reservation with the ticket: the price is the full price (#1622)
                reservation="included" if leg.get("isReservationMandatory") is True else None,
            ))
        best: dict[str, tuple[Decimal, str, str | None]] = {}
        for section_id in journey.get("sections") or []:
            for alt_id in search["sections"][section_id].get("alternatives") or []:
                alt = search["alternatives"][alt_id]
                if alt.get("isPartial"):
                    continue
                fare = search["fares"][alt["fares"][0]]
                cls = (fare.get("fareLegs") or [{}])[0].get("travelClass") or {}
                name = fare_name(data["fareTypes"][fare["fareType"]]["name"].strip(), (cls.get("name") or "").strip())
                # str() first: a JSON float such as 65.74 must not become a long binary Decimal
                amount = Decimal(str(alt["price"]["amount"])).quantize(Decimal("0.01"))
                if name not in best or amount < best[name][0]:
                    best[name] = (amount, alt["price"]["currencyCode"], travel_class(cls.get("name") or name))
        return [
            OfferIn(
                external_id=journey.get("id"),
                price_amount=amount,
                price_currency=cur,
                fare_name=name,
                travel_class=tc,
                legs=legs,
                booking_url=BOOKING_URL,
            )
            for name, (amount, cur, tc) in best.items()
        ]
