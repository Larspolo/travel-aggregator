"""Merge all data of one trip into another trip in one transaction (#1261): itineraries (one per journey by the
fingerprint), fares and price rows, flags, captures and day prices. Then delete the source trip."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Capture, DayPrice, Itinerary, Trip


def is_linked(session: Session, trip: Trip) -> bool:
    """True when the trip is a return, a split part, or has one (the rule of `_check`)."""
    return (
        trip.return_of_id is not None
        or trip.split_of_id is not None
        or session.scalar(select(Trip.id).where(or_(Trip.return_of_id == trip.id, Trip.split_of_id == trip.id)).limit(1))
        is not None
    )


def merge_choices(session: Session, trip: Trip) -> list[Trip]:
    """The trips that `trip` can merge into: not the trip itself; the trips that are not archived come first (#1262)."""
    others = session.scalars(select(Trip).where(Trip.id != trip.id)).all()
    return sorted(others, key=lambda t: (t.status == "archived", t.id))


def _check(session: Session, source_id: int, target_id: int) -> tuple[Trip, Trip]:
    if source_id == target_id:
        raise ValueError("the source and the target are the same trip")
    source, target = session.get(Trip, source_id), session.get(Trip, target_id)
    if source is None or target is None:
        raise ValueError("a trip does not exist")
    if is_linked(session, source):
        raise ValueError("the source trip is linked to another trip")
    return source, target


def _join(session: Session, it: Itinerary, into: Itinerary) -> None:
    """Move the fares and price rows of `it` to `into`, give its flags, then delete `it`."""
    by_key = {(f.source, f.fare_name): f for f in into.fares}
    for fare in list(it.fares):
        same = by_key.get((fare.source, fare.fare_name))
        if same is None:
            it.fares.remove(fare)
            into.fares.append(fare)
            continue
        target_rows = same.prices  # load before the moves: a lazy load would autoflush the orphans (#1287)
        for row in list(fare.prices):
            fare.prices.remove(row)
            target_rows.append(row)
        newest = max(same.prices, key=lambda p: (p.captured_at, p.id or 0))
        same.latest_price, same.currency, same.latest_captured_at = newest.price, newest.currency, newest.captured_at
    into.pinned, into.booked, into.hidden = into.pinned or it.pinned, into.booked or it.booked, into.hidden or it.hidden
    into.note = into.note or it.note
    if into.booked_price is None and it.booked_price is not None:
        into.booked_price, into.booked_currency, into.booked_at = it.booked_price, it.booked_currency, it.booked_at
    if into.cancelled_at is None and it.cancelled_at is not None:
        into.cancelled_at, into.refund_price = it.cancelled_at, it.refund_price  # the cancel with its refund (#1688)
    if into.delay_min is None and it.delay_min is not None:
        into.delay_min, into.claim_paid_at = it.delay_min, it.claim_paid_at  # the delay claim (#1691)
    into.first_seen_at = min(into.first_seen_at, it.first_seen_at)
    into.last_seen_at = max(into.last_seen_at, it.last_seen_at)
    session.flush()  # the moved rows leave `it` before its delete
    session.delete(it)


def merge_trips(session: Session, source_id: int, target_id: int) -> dict[str, int]:
    """Move all data of trip `source_id` into trip `target_id` and delete the source; commit. Returns the counts.
    `ValueError` (and a rollback) for the same id, a trip that does not exist or a linked source trip."""
    try:
        source, target = _check(session, source_id, target_id)
        counts = {"moved": 0, "joined": 0, "captures": 0, "day_prices": 0}
        existing = {it.fingerprint: it for it in target.itineraries}
        for it in list(source.itineraries):
            same = existing.get(it.fingerprint)
            if same is None:
                it.trip_id = target_id
                counts["moved"] += 1
            else:
                _join(session, it, same)
                counts["joined"] += 1
        session.flush()
        session.expire(source, ["itineraries"])
        for cap in session.scalars(select(Capture).where(Capture.trip_id == source_id)):
            cap.trip_id = target_id
            counts["captures"] += 1
        days = {(d.source, d.day): d for d in session.scalars(select(DayPrice).where(DayPrice.trip_id == target_id))}
        for d in session.scalars(select(DayPrice).where(DayPrice.trip_id == source_id)).all():
            old = days.get((d.source, d.day))
            if old is None:
                d.trip_id = target_id
            elif d.captured_at > old.captured_at:
                old.price, old.currency, old.captured_at, old.capture_id = d.price, d.currency, d.captured_at, d.capture_id
                session.delete(d)
            else:
                session.delete(d)
            counts["day_prices"] += 1
        session.flush()
        session.delete(source)
        session.commit()
        return counts
    except Exception:
        session.rollback()
        raise
