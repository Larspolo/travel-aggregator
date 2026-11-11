"""The parser of a Flixbus search response (`GET /search/service/v4/search`, tests/fixtures/flixbus.com/README.md).

One offer per connection of `trips[].results` with status `available`. The times have the offset of the local city
time. The currency is the `currency` query parameter of the URL (the response has none). The fare name is the
`transfer_type` (the response has no fare name). The parser sends no request (P1)."""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from app.parsers import ParseResult, count, seats
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


def travelers(url: Any) -> int | None:
    """The sum of the values of the JSON `products` query parameter (#764): `{"adult":1}` gives 1."""
    if not isinstance(url, str):
        return None
    try:
        products = json.loads((parse_qs(urlparse(url).query).get("products") or [""])[0])
        return count(sum(v for v in products.values() if isinstance(v, int))) if isinstance(products, dict) else None
    except (ValueError, TypeError):
        return None


def external_id(uid: Any) -> str | None:
    """The uid of a connection; a transfer uid is longer than 200 characters: then its hash."""
    if not isinstance(uid, str) or not uid:
        return None
    return uid if len(uid) <= 200 else "sha256:" + hashlib.sha256(uid.encode()).hexdigest()


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _day(value: Any) -> date | None:
    """The local date of an ISO time with an offset (`2026-12-01T07:15:00+01:00`), else None."""
    try:
        return aware(value).date() if isinstance(value, str) else None
    except ValueError:
        return None


def _no_bikes_period(response: dict) -> tuple[date, date] | None:
    """The `no_bikes_period` of the response (`from` and `to` as DD-MM-YYYY), else None."""
    period = response.get("no_bikes_period")
    if not isinstance(period, dict):
        return None
    try:
        return (datetime.strptime(period["from"], "%d-%m-%Y").date(),
                datetime.strptime(period["to"], "%d-%m-%Y").date())
    except (KeyError, TypeError, ValueError):
        return None


def bicycle(conn: dict, response: dict) -> str | None:
    """The bicycle transport of a connection (#2459): "no", "reservation", or None when the values are not there (P5)."""
    restrictions, available, departure = (_dict(conn.get(k)) for k in ("restrictions", "available", "departure"))
    allowed = restrictions.get("bikes_allowed")
    slots = available.get("bike_slots")
    slots = slots if isinstance(slots, int) and not isinstance(slots, bool) else None
    day = _day(departure.get("date"))
    period = _no_bikes_period(response)
    in_period = bool(day and period and period[0] <= day <= period[1])
    if allowed is False or slots == 0 or in_period:
        return "no"
    if allowed is True and slots is not None and slots > 0:
        return "reservation"
    return None


class FlixbusParser:
    source = "flixbus.com"
    version = "1.2.0"
    # the personal keys beyond PERSONAL_KEYS (#1903): none in the fixtures (the `address` is already REDACTED)
    redact_keys: frozenset[str] = frozenset()
    # the query names of the search URL that the parser reads, or that name the search (#1903)
    url_keep: frozenset[str] = frozenset({
        "from_city_id", "to_city_id", "departure_date", "products", "currency", "locale", "search_by",
        "include_after_midnight_rides", "disable_distribusion_trips", "disable_global_trips", "disable_trips",
    })
    hosts = ("global.api.flixbus.com",)
    paths = ("/search/service/v4/search",)
    group_price = True  # the price is for all travelers of the search: `total` (#1026; the fixture README)

    def parse(self, raw: Any) -> ParseResult:
        """Offers of a capture {"url", "request", "response"} or of the response body only."""
        if not isinstance(raw, dict):
            raise ValueError("the flixbus.com payload is not an object")
        response = raw.get("response", raw)
        trips = response.get("trips") if isinstance(response, dict) else None
        if not isinstance(trips, list):
            raise ValueError("the flixbus.com payload has no trips list")
        cur = currency(raw.get("url"))
        result = ParseResult(travelers=travelers(raw.get("url")))
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
            seats_left=seats((conn.get("available") or {}).get("seats")),
            bike=bicycle(conn, response),
            legs=legs,
            booking_url=BOOKING_URL,
        )
