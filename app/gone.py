"""Fares that a newer capture of the same source did not show again in its departure span (#1385, epic #1384)."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Capture, Fare, Itinerary


@dataclass(frozen=True)
class GoneMark:
    source: str
    captured_at: datetime  # of the newest capture that did not show the fare


def gone_fares(session: Session, trip_ids) -> dict[int, GoneMark]:
    """The key is Fare.id. The span of a capture is the first and the last departure of its offers (inclusive,
    `Capture.depart_from` and `depart_to`, #1404: also when all its prices are steady). Only captures of the same
    source and trip, with no mismatch, newer than the fare. 2 statements."""
    trip_ids = list(trip_ids)
    if not trip_ids:
        return {}
    spans = session.execute(
        select(Capture.trip_id, Capture.source, Capture.captured_at, Capture.depart_from, Capture.depart_to)
        .where(Capture.trip_id.in_(trip_ids), Capture.mismatch.is_(None), Capture.depart_from.is_not(None))
    ).all()
    by_key = defaultdict(list)
    for trip_id, source, captured_at, low, high in spans:
        by_key[(trip_id, source)].append((captured_at, low, high))
    if not by_key:
        return {}
    fares = session.execute(
        select(Fare.id, Fare.source, Fare.latest_captured_at, Itinerary.trip_id, Itinerary.depart_at)
        .join(Itinerary, Itinerary.id == Fare.itinerary_id)
        .where(Itinerary.trip_id.in_(trip_ids))
    ).all()
    marks: dict[int, GoneMark] = {}
    for fare_id, source, latest, trip_id, depart in fares:
        hits = [c for c, low, high in by_key.get((trip_id, source), ()) if c > latest and low <= depart <= high]
        if hits:
            marks[fare_id] = GoneMark(source=source, captured_at=max(hits))
    return marks
