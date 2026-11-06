"""The parser of an NS International search response (`POST /api/v2/sales/traveloffers/search`,
tests/fixtures/nsinternational.com/README.md).

The payload has local times with no offset. The `country` of the station gives its timezone (a zone, not the fixed
`GMT+01:00` string, so that summer time is correct). The payload has only the first departure and the last arrival:
the legs between them get the departure time and an unknown change station. The parser sends no request (P1)."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.parsers import ParseResult
from app.schemas import LegIn, OfferIn, _short_reason

DEFAULT_TZ = "Europe/Amsterdam"
COUNTRY_TZ = {
    "NL": "Europe/Amsterdam", "GB": "Europe/London", "DE": "Europe/Berlin", "FR": "Europe/Paris",
    "BE": "Europe/Brussels", "LU": "Europe/Luxembourg", "CH": "Europe/Zurich", "AT": "Europe/Vienna",
    "IT": "Europe/Rome", "DK": "Europe/Copenhagen", "CZ": "Europe/Prague", "PL": "Europe/Warsaw",
}
CHANGE_STATION = "change station"
FLEX = {"NON_FLEXIBLE": "non-flexible", "SEMI_FLEXIBLE": "semi-flexible", "FULL_FLEXIBLE": "flexible"}
BOOKING_URL = "https://www.nsinternational.com/"


def local_time(station: dict, kind: str) -> datetime:
    naive = datetime.fromisoformat(station[kind]["plannedLocalDateTime"])
    if naive.tzinfo is not None:
        return naive
    return naive.replace(tzinfo=ZoneInfo(COUNTRY_TZ.get(station.get("country") or "", DEFAULT_TZ)))


class NsParser:
    source = "nsinternational.com"
    version = "1.0.0"

    def parse(self, raw: Any) -> ParseResult:
        """Offers of a capture {"request", "response"} or of the response body only: one per fare."""
        if not isinstance(raw, dict):
            raise ValueError("the nsinternational.com payload is not an object")
        response = raw.get("response", raw)
        data = response.get("data") if isinstance(response, dict) else None
        conns = data.get("travelOffers") if isinstance(data, dict) else None
        if not isinstance(conns, list):
            raise ValueError("the nsinternational.com payload has no data.travelOffers list")
        result = ParseResult()
        for i, conn in enumerate(conns):
            try:
                result.offers.extend(self._offers(conn))
            except ValidationError as e:
                result.errors.append({"index": i, "reason": _short_reason(e)})
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                result.errors.append({"index": i, "reason": f"bad connection: {type(e).__name__} {e}"[:200]})
        return result

    def _offers(self, conn: dict) -> list[OfferIn]:
        it = conn["itinerary"]
        orig, dest = it["origin"], it["destination"]
        dep, arr = local_time(orig, "departure"), local_time(dest, "arrival")
        trains = [m for m in it["modalities"] if m.get("type") != "TRANSFER"]
        if not trains:
            raise ValueError("no train leg")
        legs = []
        for k, m in enumerate(trains):
            first, last = k == 0, k == len(trains) - 1
            legs.append(LegIn(
                mode="bus" if m.get("type") == "BUS" else "train",
                carrier=m.get("name") or m.get("code"),
                service_no=m.get("number"),
                from_name=orig["name"] if first else CHANGE_STATION,
                from_code=orig.get("code") if first else None,
                to_name=dest["name"] if last else CHANGE_STATION,
                to_code=dest.get("code") if last else None,
                depart_at=dep,
                arrive_at=arr if last else dep,
            ))
        offers = []
        for o in conn["offers"]:
            price = o["totalPrice"]
            flex = FLEX.get(o.get("flexLevel"), (o.get("flexLevel") or "").lower().replace("_", "-"))
            offers.append(OfferIn(
                external_id=conn.get("id"),
                # str() first: a JSON float such as 107.99 must not become a long binary Decimal
                price_amount=Decimal(str(price["amount"])).quantize(Decimal("0.01")),
                price_currency=price.get("currency") or "EUR",
                # one fare per (itinerary, source, fare name): the name alone repeats for each flex level
                fare_name=", ".join(x for x in [(o.get("name") or "").strip(), flex] if x) or None,
                flexibility=flex,
                legs=legs,
                booking_url=BOOKING_URL,
            ))
        return offers
