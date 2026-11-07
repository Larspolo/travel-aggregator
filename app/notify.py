"""Push messages for price drops of pinned fares (#512). The first channel is ntfy: one POST of plain text to the
topic URL that the owner sets on the settings page. `messages()` reads the settings in the request; `deliver()`
runs after the response (a background task, with no database session). A failure is logged and never raised, so
the userscript gets the same response."""

import logging
import urllib.request
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Setting, Trip

log = logging.getLogger(__name__)

CHANNEL_KEY = "notify_channel"
NTFY_URL_KEY = "ntfy_url"
CHANNELS = ("none", "ntfy")
TIMEOUT_S = 5


@dataclass(frozen=True)
class PriceDrop:
    trip_id: int
    fare_name: str | None
    source: str
    currency: str
    old_price: Decimal
    new_price: Decimal


@dataclass(frozen=True)
class Message:
    url: str
    title: str
    text: str
    click: str


def setting(session: Session, key: str, default: str = "") -> str:
    row = session.get(Setting, key)
    return row.value if row is not None else default


def _line(d: PriceDrop) -> str:
    return f"{d.fare_name or '-'} ({d.source}): {d.currency} {d.old_price} → {d.currency} {d.new_price}"


def messages(session: Session, drops: list[PriceDrop], base_url: str) -> list[Message]:
    """One message per trip with all the drops of one ingest; none when the channel is not ntfy."""
    if not drops or setting(session, CHANNEL_KEY, "none") != "ntfy":
        return []
    url = setting(session, NTFY_URL_KEY)
    if not url.startswith("https://"):
        return []
    out = []
    for trip_id in dict.fromkeys(d.trip_id for d in drops):
        trip = session.get(Trip, trip_id)
        title = trip.title if trip is not None else f"trip {trip_id}"
        out.append(Message(url=url, title=f"Price drop: {title}",
                           text="\n".join(_line(d) for d in drops if d.trip_id == trip_id),
                           click=f"{base_url.rstrip('/')}/trips/{trip_id}"))
    return out


def post(url: str, text: str, headers: dict[str, str]) -> None:
    """The ntfy sender: one POST of the text. The tests replace it with a double (no request from CI)."""
    req = urllib.request.Request(url, data=text.encode(), method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT_S):  # noqa: S310 (save_settings accepts only https://)
        pass


def deliver(msgs: list[Message]) -> None:
    for m in msgs:
        try:
            # an HTTP header is latin-1: ntfy reads a UTF-8 title from the raw bytes
            post(m.url, m.text, {"Title": m.title.encode().decode("latin-1"), "Click": m.click})
        except Exception as e:  # noqa: BLE001 (a failed send must not break the ingest)
            log.warning("price drop message not sent: %s", e)
