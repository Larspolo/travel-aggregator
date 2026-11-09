"""Fares whose latest price cannot be right: €0, or a price below a fifth or above five times the last usable price (#1604, epic #1603)."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fare, FarePrice, Itinerary

FACTOR = 5


@dataclass(frozen=True)
class SuspectMark:
    price: Decimal  # the latest price of the fare
    last: Decimal | None  # the usable price that it is compared with; None for a €0 price with no such price
    currency: str


def implausible(price: Decimal, last: Decimal | None) -> bool:
    """A price is implausible when it is 0, or when it is below a fifth or above five times `last` (None: no baseline)."""
    if price == 0:
        return True
    if last is None or last == 0:
        return False
    return price * FACTOR < last or price > last * FACTOR


def _baseline(prices: list[tuple[Decimal, str]], currency: str) -> Decimal | None:
    """The newest usable price before the latest capture, in `currency`. A 0 or implausible row is skipped,
    so a later plausible price is compared with the price before the wrong row (the epic's rule)."""
    baseline = None
    for price, cur in prices:
        if cur != currency or price == 0:
            continue
        if baseline is None or not implausible(price, baseline):
            baseline = price
    return baseline


def _suspect(session: Session, trip_ids) -> tuple[dict[int, SuspectMark], dict[int, int | None]]:
    """The marks, and for each marked fare the capture of its latest price row (2 statements)."""
    trip_ids = list(trip_ids)
    if not trip_ids:
        return {}, {}
    fares = session.execute(
        select(Fare.id, Fare.latest_price, Fare.currency, Fare.latest_captured_at)
        .join(Itinerary, Itinerary.id == Fare.itinerary_id)
        .where(Itinerary.trip_id.in_(trip_ids))
    ).all()
    if not fares:
        return {}, {}
    rows = session.execute(
        select(FarePrice.fare_id, FarePrice.price, FarePrice.currency, FarePrice.captured_at, FarePrice.id,
               FarePrice.capture_id)
        .join(Fare, Fare.id == FarePrice.fare_id)
        .join(Itinerary, Itinerary.id == Fare.itinerary_id)
        .where(Itinerary.trip_id.in_(trip_ids))
    ).all()
    by_fare = defaultdict(list)
    for fare_id, price, currency, captured_at, row_id, capture_id in sorted(rows, key=lambda r: (r[3], r[4])):
        by_fare[fare_id].append((captured_at, price, currency, capture_id))
    marks: dict[int, SuspectMark] = {}
    captures: dict[int, int | None] = {}
    for fare_id, latest, currency, latest_at in fares:
        history = by_fare.get(fare_id, [])
        older = [(p, c) for at, p, c, _ in history if at < latest_at]
        last = _baseline(older, currency)
        if implausible(latest, last):
            marks[fare_id] = SuspectMark(price=latest, last=last, currency=currency)
            latest_rows = [cap for at, _, _, cap in history if at == latest_at]
            captures[fare_id] = latest_rows[-1] if latest_rows else None
    return marks, captures


def suspect_fares(session: Session, trip_ids) -> dict[int, SuspectMark]:
    """The key is Fare.id. Only the fares of the given trips. 2 statements for any number of trips."""
    return _suspect(session, trip_ids)[0]


def suspect_counts(session: Session, trip_ids) -> dict[int, int]:
    """The key is Capture.id: how many of its fares have the mark (the fare belongs to the capture of its latest
    price row). Only captures that have a marked fare are in the result. 2 statements for any number of trips."""
    _, captures = _suspect(session, trip_ids)
    counts: dict[int, int] = defaultdict(int)
    for capture_id in captures.values():
        if capture_id is not None:
            counts[capture_id] += 1
    return dict(counts)
