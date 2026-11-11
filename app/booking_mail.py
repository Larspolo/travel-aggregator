"""Read the schema.org reservations of a saved confirmation e-mail (#2296).

The mail is untrusted data (P5): only the standard library reads it, with a size limit. No database, no route.
"""

from __future__ import annotations

import email
import email.policy
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

from app.schemas import MAX_MAIL_BYTES

# @type -> (mode, trip type keys: origin, destination, number)
_KINDS = {
    "TrainReservation": ("train", "departureStation", "arrivalStation", "trainNumber"),
    "BusReservation": ("bus", "departureBusStop", "arrivalBusStop", "busNumber"),
    "FlightReservation": ("flight", "departureAirport", "arrivalAirport", "flightNumber"),
}


@dataclass
class MailLeg:
    mode: str
    origin: str | None
    destination: str | None
    depart_at: datetime
    arrive_at: datetime | None
    carrier: str | None
    number: str | None


@dataclass
class MailBooking:
    code: str | None
    price: Decimal | None
    currency: str | None
    legs: list[MailLeg] = field(default_factory=list)


class _LdJson(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[str] = []
        self._buf: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "script" and (dict(attrs).get("type") or "").strip().lower() == "application/ld+json":
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "script" and self._buf is not None:
            self.blocks.append("".join(self._buf))
            self._buf = None

    def handle_data(self, data):
        if self._buf is not None:
            self._buf.append(data)


def _types(item: dict) -> set[str]:
    t = item.get("@type")
    return {t} if isinstance(t, str) else {x for x in t if isinstance(x, str)} if isinstance(t, list) else set()


def _items(node):
    if isinstance(node, list):
        for x in node:
            yield from _items(x)
    elif isinstance(node, dict):
        if "@graph" in node:
            yield from _items(node["@graph"])
        yield node


def _name(node, *keys: str) -> str | None:
    if isinstance(node, str):
        return node or None
    if isinstance(node, dict):
        for k in keys:
            v = node.get(k)
            if isinstance(v, str) and v:
                return v
    return None


def _time(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo is not None and t.utcoffset() is not None else None


def _price(res: dict) -> tuple[Decimal | None, str | None]:
    value = res.get("totalPrice", res.get("price"))
    currency = res.get("priceCurrency")
    if isinstance(value, dict):  # a PriceSpecification
        currency = value.get("priceCurrency", currency)
        value = value.get("price")
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None, None
    try:
        price = Decimal(str(value).strip())
    except InvalidOperation:
        return None, None
    if not price.is_finite():
        return None, None
    return price, currency if isinstance(currency, str) else None


def _leg(res: dict, kind: str) -> MailLeg | None:
    mode, dep_key, arr_key, num_key = _KINDS[kind]
    trip = res.get("reservationFor")
    if not isinstance(trip, dict):
        return None
    depart = _time(trip.get("departureTime"))
    if depart is None:
        return None
    arrive = None
    if trip.get("arrivalTime") is not None:
        arrive = _time(trip.get("arrivalTime"))
        if arrive is None:
            return None
    keys = ("name", "iataCode") if mode == "flight" else ("name",)
    carrier = _name(trip.get("airline") if mode == "flight" else trip.get("provider"), "name", "iataCode")
    if carrier is None and mode != "flight":
        carrier = _name(trip.get("provider"), "name")
    number = trip.get(num_key)
    return MailLeg(
        mode=mode,
        origin=_name(trip.get(dep_key), *keys),
        destination=_name(trip.get(arr_key), *keys),
        depart_at=depart,
        arrive_at=arrive,
        carrier=carrier,
        number=str(number) if isinstance(number, (str, int)) and not isinstance(number, bool) else None,
    )


def read_booking(raw: bytes) -> MailBooking | None:
    """Return the booking of the mail, or None when it has no usable reservation markup."""
    if len(raw) > MAX_MAIL_BYTES:
        raise ValueError(f"mail is larger than {MAX_MAIL_BYTES} bytes")
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    found: list[tuple[dict, str, MailLeg]] = []
    for part in msg.walk():
        if part.get_content_type() != "text/html":
            continue
        try:
            html = part.get_content()
        except (LookupError, ValueError):
            continue
        parser = _LdJson()
        parser.feed(html)
        parser.close()
        for block in parser.blocks:
            try:
                data = json.loads(block)
            except ValueError:
                continue
            for item in _items(data):
                kind = next((k for k in _KINDS if k in _types(item)), None)
                if kind is None:
                    continue
                leg = _leg(item, kind)
                if leg is not None:
                    found.append((item, kind, leg))
    if not found:
        return None
    first = found[0][0]
    code = first.get("reservationNumber")
    code = code if isinstance(code, str) and code else None
    same = [(r, leg) for r, _, leg in found if (r.get("reservationNumber") or None) == code]
    price, currency = next(((p, c) for p, c in (_price(r) for r, _ in same) if p is not None), (None, None))
    legs = sorted((leg for _, leg in same), key=lambda x: x.depart_at)
    return MailBooking(code=code, price=price, currency=currency, legs=legs)
