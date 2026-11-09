"""The parser of a Kiwi.com search response: one way (SearchOneWayItinerariesQuery) or return
(SearchReturnItinerariesQuery, #1004), tests/fixtures/kiwi.com/README.md.

A return itinerary gives an offer of its outbound flights only, with the price of the return ticket and a fare name
with " return": an offer of a trip has one direction (a return trip is a second trip, #340), and Kiwi.com sells the
two directions as one ticket.

Each itinerary is one journey. Each fare (`bookingOptions.edges[].node`) is one offer. The times have no airport time
zone table: the offset of an end of a segment is `localTime` minus `utcTimeIso`. The parser sends no request (P1).
Baggage (`bagsInfo`) gives the checked bags of each fare (#1526)."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.parsers import ParseResult, count
from app.schemas import LegIn, OfferIn, _short_reason

log = logging.getLogger(__name__)
BOOKING_BASE = "https://www.kiwi.com"


def _travelers(passengers: Any) -> int | None:
    """The travelers of the request (#766): the sum of adults, children and infants; None when a count is not an
    integer or the sum is outside 1 to 9 (P5: the payload is untrusted)."""
    if not isinstance(passengers, dict):
        return None
    parts = [passengers.get(k) for k in ("adults", "children", "infants")]
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in parts):
        return None
    return count(sum(parts))


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


def _bags(info: Any) -> tuple[int | None, Decimal | None]:
    """The included checked bags and the lowest price of one checked bag (`checkedBagTiers`), else None (fail soft)."""
    if not isinstance(info, dict):
        return None, None
    included = info.get("includedCheckedBags")
    if not isinstance(included, int) or isinstance(included, bool):
        included = None
    prices = []
    for tier in info.get("checkedBagTiers") or []:
        amount = ((tier or {}).get("tierPrice") or {}).get("amount")
        if amount is not None:
            try:
                prices.append(Decimal(str(amount)).quantize(Decimal("0.01")))
            except (ArithmeticError, ValueError):
                continue
    return included, (min(prices) if prices else None)


class KiwiParser:
    source = "kiwi.com"
    version = "1.3.0"
    group_price = True  # the price is for all travelers of the request (#1027; the fixture README)

    def parse(self, raw: Any) -> ParseResult:
        """Offers of a capture {"currency", "response"} or of the response body only: one per fare."""
        if not isinstance(raw, dict):
            raise ValueError("the kiwi.com payload is not an object")
        response = raw.get("response", raw)
        search = response.get("data") if isinstance(response, dict) else None
        if isinstance(search, dict) and "returnItineraries" in search:
            search = search.get("returnItineraries")
        else:
            search = search.get("onewayItineraries") if isinstance(search, dict) else None
        itins = search.get("itineraries") if isinstance(search, dict) else None
        if not isinstance(itins, list):
            raise ValueError("the kiwi.com payload has no data.onewayItineraries or data.returnItineraries itineraries list")
        currency = str(raw.get("currency") or "EUR").upper()
        result = ParseResult(travelers=_travelers(raw.get("passengers")))
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
        sector = it["outbound"] if "outbound" in it else it["sector"]
        for k, sector_segment in enumerate(sector["sectorSegments"]):
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
        included, bag_price = _bags(it.get("bagsInfo"))
        offers, suffix = [], " return" if "outbound" in it else ""
        for edge in it["bookingOptions"]["edges"]:
            node = edge["node"]
            offers.append(OfferIn(
                price_amount=Decimal(str(node["price"]["amount"])).quantize(Decimal("0.01")),
                price_currency=currency,
                fare_name=(node["itineraryProvider"]["code"] or "") + suffix or None,
                legs=legs,
                booking_url=BOOKING_BASE + node["bookingUrl"],
                checked_bags_included=included,
                checked_bag_price=bag_price,
            ))
        return offers
