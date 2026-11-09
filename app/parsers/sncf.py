"""The parser of an SNCF Connect search response (`POST /bff/api/v1/itineraries`, tests/fixtures/sncf-connect.com/README.md).

One itinerary per bookable proposal of `longDistance.proposals.proposals`, one offer per fare of its first-class and
second-class offers. The times are local time of France with no offset: the parser adds the offset of Europe/Paris
for the date of each leg. The price is the French `priceLabel` ("25,50 €"), never the float `bestPrice.value`.
The parser sends no request (P1)."""

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.parsers import ParseResult
from app.schemas import LegIn, OfferIn, _short_reason

PARIS = ZoneInfo("Europe/Paris")
TRAVEL_CLASSES = {"FIRST": "first", "SECOND": "standard"}
BOOKING_URL = "https://www.sncf-connect.com/"
PRICE = re.compile(r"^(\d{1,6})(?:,(\d{1,2}))?$")


def price(label: Any) -> Decimal:
    """'25,50 €' gives Decimal('25.50'); the label has a (no-break) space before the euro sign."""
    if not isinstance(label, str):
        raise ValueError(f"a price label that is not text: {label!r}")
    text = re.sub(r"[\s  ]", "", label)
    if not text.endswith("€"):
        raise ValueError(f"a price that is not in EUR: {label!r}")
    m = PRICE.match(text[:-1])
    if not m:
        raise ValueError(f"a bad price label: {label!r}")
    return Decimal(f"{m[1]}.{(m[2] or '0').ljust(2, '0')}")


def local(day: date, label: str) -> datetime:
    return datetime.combine(day, time.fromisoformat(label), tzinfo=PARIS)


def service_no(transporter: dict) -> str | None:
    number = str(transporter.get("number") or "").replace("n°", "").strip()
    return number or None


class SncfParser:
    source = "sncf-connect.com"
    version = "1.0.0"
    hosts = ("www.sncf-connect.com",)
    paths = ("/bff/api/v1/itineraries",)

    @staticmethod
    def har_raw(url, method, request, response):
        """The raw form of the userscript: only the search keys of the request body."""
        keep = {k: request[k] for k in ("schedule", "mainJourney") if k in request} if isinstance(request, dict) else None
        return {"url": url, "method": method, "request": keep, "response": response}

    def parse(self, raw: Any) -> ParseResult:
        """Offers of a capture {"url", "request", "response"} or of the response body only."""
        if not isinstance(raw, dict):
            raise ValueError("the sncf-connect.com payload is not an object")
        response = raw.get("response", raw)
        props = response.get("longDistance") if isinstance(response, dict) else None
        props = props.get("proposals") if isinstance(props, dict) else None
        props = props.get("proposals") if isinstance(props, dict) else None
        if not isinstance(props, list):
            raise ValueError("the sncf-connect.com payload has no longDistance.proposals.proposals list")
        result = ParseResult(travelers=1 if "response" in raw else None)
        for i, prop in enumerate(props):
            try:
                if not prop["status"]["isBookable"]:
                    continue
                result.offers.extend(self._offers(prop))
            except ValidationError as e:
                result.errors.append({"index": i, "reason": _short_reason(e)})
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                result.errors.append({"index": i, "reason": f"bad proposal: {type(e).__name__} {e}"[:200]})
        return result

    def _legs(self, prop: dict) -> list[LegIn]:
        legs = []
        last = None
        for step in prop["globalTimeline"]["steps"]:
            train = step.get("train")
            if train is None:
                continue
            day = date.fromisoformat(train["tripIv"]["vehicleDetails"]["request"]["date"])
            dep = local(day, train["departure"]["timeLabel"])
            if last is not None and dep < last:
                dep += timedelta(days=1)
            arr = local(dep.date(), train["arrival"]["timeLabel"])
            if arr < dep:
                arr = local(dep.date() + timedelta(days=1), train["arrival"]["timeLabel"])
            last = arr
            tr = train["transporter"]
            legs.append(LegIn(
                mode="train",
                carrier=tr.get("description") or None,
                service_no=service_no(tr),
                from_name=train["departure"]["stationLabel"],
                from_code=None,
                to_name=train["arrival"]["stationLabel"],
                to_code=None,
                depart_at=dep,
                arrive_at=arr,
            ))
        if not legs:
            raise ValueError("a proposal with no train step")
        return legs

    def _offers(self, prop: dict) -> list[OfferIn]:
        legs = self._legs(prop)
        offers = []
        for group in ("firstComfortClassOffers", "secondComfortClassOffers"):
            for offer in (prop.get(group) or {}).get("offers") or []:
                fares = [s.get("fareName") for f in offer.get("travelersFares") or [] for s in f.get("segmentFares") or []]
                names = list(dict.fromkeys(n for n in fares if n))
                offers.append(OfferIn(
                    external_id=prop.get("travelId") or None,
                    price_amount=price(offer["priceLabel"]),
                    price_currency="EUR",
                    fare_name=" + ".join(names) or None,
                    travel_class=TRAVEL_CLASSES.get(offer["comfortClass"]["code"]),
                    legs=legs,
                    booking_url=BOOKING_URL,
                ))
        return offers
