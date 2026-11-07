"""The parser of a Flixbus search response (`GET /search/service/v4/search`, tests/fixtures/flixbus.com/README.md).

One offer per connection of `trips[].results` with status `available`. The times have the offset of the local city
time. The currency is the `currency` query parameter of the URL (the response has none). The fare name is the
`transfer_type` (the response has no fare name). The parser sends no request (P1)."""

import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from app.parsers import ParseResult
from app.schemas import LegIn, OfferIn, _short_reason

BOOKING_URL = "https://www.flixbus.com/"
DEFAULT_CURRENCY = "EUR"


def aware(value: str) -> datetime:
    t = datetime.fromisoformat(value)
    if t.tzinfo is None:
        raise ValueError(f"a time with no offset: {value}")
    return t


def currency(url: Any) -> str:
    if not isinstance(url, str):
        return DEFAULT_CURRENCY
    return (parse_qs(urlparse(url).query).get("currency") or [DEFAULT_CURRENCY])[0].upper()


def external_id(uid: Any) -> str | None:
    """The uid of a connection; a transfer uid is longer than 200 characters: then its hash."""
    if not isinstance(uid, str) or not uid:
        return None
    return uid if len(uid) <= 200 else "sha256:" + hashlib.sha256(uid.encode()).hexdigest()


class FlixbusParser:
    source = "flixbus.com"
    version = "1.0.0"

    def parse(self, raw: Any) -> ParseResult:
        """Offers of a capture {"url", "request", "response"} or of the response body only."""
        if not isinstance(raw, dict):
            raise ValueError("the flixbus.com payload is not an object")
        response = raw.get("response", raw)
        trips = response.get("trips") if isinstance(response, dict) else None
        if not isinstance(trips, list):
            raise ValueError("the flixbus.com payload has no trips list")
        cur = currency(raw.get("url"))
        result = ParseResult()
        conns = [c for t in trips for c in ((t or {}).get("results") or {}).values()]
        for i, conn in enumerate(conns):
            try:
                if conn.get("status") != "available":
                    continue
                result.offers.append(self._offer(conn, response, cur))
            except ValidationError as e:
                result.errors.append({"index": i, "reason": _short_reason(e)})
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                result.errors.append({"index": i, "reason": f"bad connection: {type(e).__name__} {e}"[:200]})
        return result

    def _offer(self, conn: dict, response: dict, cur: str) -> OfferIn:
        stations = response.get("stations") or {}
        operators = response.get("operators") or {}
        legs = []
        for leg in conn["legs"]:
            dep, arr = leg["departure"], leg["arrival"]
            op = operators.get(leg.get("operator_id")) or {}
            legs.append(LegIn(
                mode="train" if leg.get("means_of_transport") == "train" else "bus",
                carrier=op.get("label") or leg.get("operator_id"),
                service_no=leg.get("ride_id"),
                from_name=stations[dep["station_id"]]["name"],
                from_code=None,
                to_name=stations[arr["station_id"]]["name"],
                to_code=None,
                depart_at=aware(dep["date"]),
                arrive_at=aware(arr["date"]),
            ))
        return OfferIn(
            external_id=external_id(conn.get("uid")),
            # str() first: a JSON float such as 25.48 must not become a long binary Decimal
            price_amount=Decimal(str(conn["price"]["total"])).quantize(Decimal("0.01")),
            price_currency=cur,
            fare_name=conn.get("transfer_type") or None,
            legs=legs,
            booking_url=BOOKING_URL,
        )
