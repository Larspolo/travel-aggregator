"""Push messages for price drops of pinned fares (#512). The first channel is ntfy: one POST of plain text to the
topic URL that the owner sets on the settings page. The second channel is e-mail (#513), by the SMTP server
of the environment (P5: no password in the database). The third channel is Web Push (#514): one encrypted message
to each browser that the owner subscribed on the settings page (RFC 8291 with `pywebpush`: the standard library has
no ECDH or AES-GCM). `messages()` reads the settings in the request; `deliver()` runs after the response (a
background task with a new database session, only to delete the subscriptions that the push service no longer
knows). A failure is logged and never raised, so the userscript gets the same response.
`python3 -m app.notify` prints a new VAPID key pair for the environment."""

import base64
import json
import logging
import smtplib
import urllib.request
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from decimal import Decimal
from email.message import EmailMessage

from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PushSubscription, Setting, Trip

log = logging.getLogger(__name__)

CHANNEL_KEY = "notify_channel"
NTFY_URL_KEY = "ntfy_url"
EMAIL_KEY = "notify_email"
CHANNELS = ("none", "ntfy", "email", "webpush")
GONE = (404, 410)  # the push service no longer knows the subscription
TIMEOUT_S = 5


@dataclass(frozen=True)
class PriceDrop:
    trip_id: int
    fare_name: str | None
    source: str
    currency: str
    old_price: Decimal | None  # None: a new fare, or the old price was in another currency
    new_price: Decimal
    target: bool = False  # the new price crosses the target price of the trip (#848)


@dataclass(frozen=True)
class Message:
    channel: str
    url: str  # the ntfy topic URL, the e-mail address, or the endpoint of the push subscription
    title: str
    text: str
    click: str
    keys: dict[str, str] = field(default_factory=dict)  # webpush: p256dh and auth of the subscription


def setting(session: Session, key: str, default: str = "") -> str:
    row = session.get(Setting, key)
    return row.value if row is not None else default


def _line(d: PriceDrop) -> str:
    if d.old_price is None:
        return f"{d.fare_name or '-'} ({d.source}): {d.currency} {d.new_price}"
    return f"{d.fare_name or '-'} ({d.source}): {d.currency} {d.old_price} → {d.currency} {d.new_price}"


def webpush_ready() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key and s.vapid_subject)


def _targets(session: Session, channel: str) -> list[tuple[str, dict[str, str]]]:
    if channel == "ntfy":
        url = setting(session, NTFY_URL_KEY)
        return [(url, {})] if url.startswith("https://") else []
    if channel == "email":
        address = setting(session, EMAIL_KEY)
        return [(address, {})] if "@" in address else []
    if channel == "webpush" and webpush_ready():
        return [(p.endpoint, {"p256dh": p.p256dh, "auth": p.auth})
                for p in session.scalars(select(PushSubscription).order_by(PushSubscription.id))]
    return []


def messages(session: Session, drops: list[PriceDrop], base_url: str) -> list[Message]:
    """One message per trip (and per subscription of webpush) with all the drops of one ingest; none for the
    channel `none`."""
    channel = setting(session, CHANNEL_KEY, "none")
    targets = _targets(session, channel) if drops else []
    out = []
    for trip_id in dict.fromkeys(d.trip_id for d in drops) if targets else ():
        trip = session.get(Trip, trip_id)
        title = trip.title if trip is not None else f"trip {trip_id}"
        mine = [d for d in drops if d.trip_id == trip_id]
        text = "\n".join(_line(d) for d in mine)
        kind = "Target price" if any(d.target for d in mine) else "Price drop"
        out += [Message(channel=channel, url=url, title=f"{kind}: {title}", text=text,
                        click=f"{base_url.rstrip('/')}/trips/{trip_id}", keys=keys) for url, keys in targets]
    return out


def post(url: str, text: str, headers: dict[str, str]) -> None:
    """The ntfy sender: one POST of the text. The tests replace it with a double (no request from CI)."""
    req = urllib.request.Request(url, data=text.encode(), method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT_S):  # noqa: S310 (save_settings accepts only https://)
        pass


def send_email(m: Message) -> None:
    """The e-mail sender: SSL on port 465, else STARTTLS. The tests replace `smtplib.SMTP` with a double."""
    cfg = get_settings()
    mail = EmailMessage()
    mail["Subject"], mail["From"], mail["To"] = m.title, cfg.smtp_from or cfg.smtp_user, m.url
    mail.set_content(f"{m.text}\n\n{m.click}\n")
    if cfg.smtp_port == 465:
        server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=TIMEOUT_S * 2)
    else:
        server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=TIMEOUT_S * 2)
    with server:
        if cfg.smtp_port != 465:
            server.starttls()
        if cfg.smtp_user:
            server.login(cfg.smtp_user, cfg.smtp_password)
        server.send_message(mail)


def push(m: Message) -> None:
    """The webpush sender: `webpush()` encrypts the message for the browser and posts it to its push service."""
    s = get_settings()
    webpush({"endpoint": m.url, "keys": m.keys}, json.dumps({"title": m.title, "body": m.text, "url": m.click}),
            vapid_private_key=s.vapid_private_key, vapid_claims={"sub": s.vapid_subject}, timeout=TIMEOUT_S, ttl=86400)


def deliver(msgs: list[Message], new_session: Callable[[], AbstractContextManager[Session]] | None = None) -> None:
    gone = []
    for m in msgs:
        try:
            if m.channel == "email":
                send_email(m)
            elif m.channel == "webpush":
                push(m)
            else:  # an HTTP header is latin-1: ntfy reads a UTF-8 title from the raw bytes
                post(m.url, m.text, {"Title": m.title.encode().decode("latin-1"), "Click": m.click})
        except WebPushException as e:
            if getattr(e.response, "status_code", None) in GONE:
                gone.append(m.url)
            else:
                log.warning("price drop message not sent: %s", e)
        except Exception as e:  # noqa: BLE001 (a failed send must not break the ingest)
            log.warning("price drop message not sent: %s", e)
    if gone and new_session is not None:
        try:
            with new_session() as session:
                session.execute(delete(PushSubscription).where(PushSubscription.endpoint.in_(gone)))
                session.commit()
            log.info("deleted %d push subscriptions that the push service no longer knows", len(set(gone)))
        except Exception as e:  # noqa: BLE001
            log.warning("push subscriptions not deleted: %s", e)


def vapid_keys() -> tuple[str, str]:
    """A new VAPID key pair (P-256) as base64url: the raw public point and the raw private value."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64(public), b64(key.private_numbers().private_value.to_bytes(32, "big"))


if __name__ == "__main__":
    public_key, private_key = vapid_keys()
    print(f"VAPID_PUBLIC_KEY={public_key}\nVAPID_PRIVATE_KEY={private_key}")
