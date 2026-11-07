"""The parser of a Kiwi.com one-way search response (SearchOneWayItinerariesQuery, tests/fixtures/kiwi.com/README.md).

Each itinerary is one journey. Each fare (`bookingOptions.edges[].node`) is one offer. The times have no airport time
zone table: the offset of an end of a segment is `localTime` minus `utcTimeIso`. The parser sends no request (P1).
Baggage (`bagsInfo`) has no field in OfferIn yet, so it is not stored (#331)."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.parsers import ParseResult
from app.schemas import LegIn, OfferIn, _short_reason

log = logging.getLogger(__name__)
BOOKING_BASE = "https://www.kiwi.com"


def _time(station: dict) -> datetime:
    """The instant of an end of a segment, in the original offset of the airport (`localTime` - `utcTimeIso`)."""
    utc = datetime.fromisoformat(station["utcTimeIso"].replace("Z", "+00:00"))
    if utc.tzinfo is None:
        raise ValueError("utcTimeIso has no offset")
    local = datetime.fromisoformat(station["localTime"])
    if local.tzinfo is not None:
        raise ValueError("localTime has an offset")
    offset = local.replace(tzinfo=None) - utc.replace(tzinfo=None)
    return utc.astimezone(timezone(offset))


class KiwiParser:
    source = "kiwi.com"
    version = "1.0.0"

    def parse(self, raw: Any) -> ParseResult:
        """Offers of a capture {"currency", "response"} or of the response body only: one per fare."""
        if not isinstance(raw, dict):
            raise ValueError("the kiwi.com payload is not an object")
        response = raw.get("response", raw)
        search = response.get("data") if isinstance(response, dict) else None
        search = search.get("onewayItineraries") if isinstance(search, dict) else None
        itins = search.get("itineraries") if isinstance(search, dict) else None
        if not isinstance(itins, list):
            raise ValueError("the kiwi.com payload has no data.onewayItineraries.itineraries list")
        currency = str(raw.get("currency") or "EUR").upper()
        result = ParseResult()
        for i, it in enumerate(itins):
            try:
                result.offers.extend(self._offers(it, currency))
            except ValidationError as e:
                reason = _short_reason(e)
                result.errors.append({"index": i, "reason": reason})
                log.warning("kiwi.com itinerary %s rejected: %s", i, reason)
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                reason = f"bad itinerary: {type(e).__name__} {e}"[:200]
                result.errors.append({"index": i, "reason": reason})
                log.warning("kiwi.com itinerary %s rejected: %s", i, reason)
        return result

    def _legs(self, it: dict) -> list[LegIn]:
        """One leg per segment. A segment with a guarantee starts a new ticket (a self-transfer, #176)."""
        legs, ticket = [], 1
        for k, sector_segment in enumerate(it["sector"]["sectorSegments"]):
            seg = sector_segment["segment"]
            if k and (sector_segment.get("guarantee") is not None or seg.get("guarantee") is not None):
                ticket += 1
            src, dst = seg["source"], seg["destination"]
            code = seg["carrier"]["code"]
            legs.append(LegIn(
                mode="flight",
                carrier=(seg["carrier"].get("name") or code) or None,
                service_no=f"{code}{seg['code']}",
                from_name=src["station"]["code"],
                from_code=src["station"]["code"],
                to_name=dst["station"]["code"],
                to_code=dst["station"]["code"],
                depart_at=_time(src),
                arrive_at=_time(dst),
                ticket=ticket,
            ))
        return legs

    def _offers(self, it: dict, currency: str) -> list[OfferIn]:
        legs = self._legs(it)
        offers = []
        for edge in it["bookingOptions"]["edges"]:
            node = edge["node"]
            offers.append(OfferIn(
                price_amount=Decimal(str(node["price"]["amount"])).quantize(Decimal("0.01")),
                price_currency=currency,
                fare_name=node["itineraryProvider"]["code"] or None,
                legs=legs,
                booking_url=BOOKING_BASE + node["bookingUrl"],
            ))
        return offers
