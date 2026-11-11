"""The empty fare and leg fields of each source (#1968): for each source and field, the fares with an empty field in
the last 14 days and in the 90 days before, and a mark when a source stopped giving the field. Stores nothing."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fare, Leg

RECENT_DAYS, BEFORE_DAYS = 14, 90
TRANSPORT_MODES = ("train", "bus", "flight", "ferry")  # legs with `car` or `other` do not count
FIELDS = {"service_no": "no service number", "carrier": "no carrier", "fare_name": "no fare name",
          "travel_class": "no travel class", "flexibility": "no flexibility"}
LEG_FIELDS = ("service_no", "carrier")


@dataclass(frozen=True)
class FieldHealth:
    source: str
    field: str
    empty: int
    total: int
    empty_before: int
    total_before: int
    mark: bool

    @property
    def text(self) -> str:
        return FIELDS[self.field]


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _span(session: Session, start: datetime, end: datetime | None) -> dict[str, dict[str, int]]:
    """For each source: the fare count (`""`) and the count of fares with each field empty. One SQL statement."""
    cond = Fare.latest_captured_at >= start
    if end is not None:
        cond = cond & (Fare.latest_captured_at < end)
    rows = session.execute(
        select(Fare.id, Fare.source, Fare.fare_name, Fare.travel_class, Fare.flexibility,
               Leg.mode, Leg.carrier, Leg.service_no)
        .outerjoin(Leg, (Leg.itinerary_id == Fare.itinerary_id) & Leg.mode.in_(TRANSPORT_MODES))
        .where(cond)).all()
    fares: dict[int, tuple[str, set[str]]] = {}
    for r in rows:
        source, empty = fares.setdefault(r.id, (r.source, {f for f in ("fare_name", "travel_class", "flexibility")
                                                           if _blank(getattr(r, f))}))
        if r.mode is not None:
            empty.update(f for f in LEG_FIELDS if _blank(getattr(r, f)))
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for source, empty in fares.values():
        counts[source][""] += 1
        for f in empty:
            counts[source][f] += 1
    return counts


def _mark(empty: int, total: int, empty_before: int, total_before: int) -> bool:
    return (total >= 5 and total_before >= 10 and empty * 2 >= total and empty_before * 10 < total_before)


def field_health(session: Session, now: datetime) -> list[FieldHealth]:
    """One row for each source with a fare in the last 14 days and each field of `FIELDS`, by source name."""
    split = now - timedelta(days=RECENT_DAYS)
    recent = _span(session, split, None)
    before = _span(session, split - timedelta(days=BEFORE_DAYS), split)
    rows = []
    for source in sorted(recent):
        r, b = recent[source], before.get(source, {})
        for f in FIELDS:
            args = (r.get(f, 0), r[""], b.get(f, 0), b.get("", 0))
            rows.append(FieldHealth(source, f, *args, _mark(*args)))
    return rows
