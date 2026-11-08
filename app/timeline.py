"""The timeline bars of the rows of a trip (#813): for each departure day, one bar per itinerary on the time axis of
that day, so that the template only draws them."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

MIN_AXIS_MIN = 6 * 60  # the shortest axis


@dataclass(frozen=True)
class LegPart:
    mode: str
    left: float  # % of the axis
    width: float  # % of the axis
    kind: str = "leg"


@dataclass(frozen=True)
class GapPart:
    from_name: str  # the transfer place
    minutes: int
    left: float
    width: float
    kind: str = "gap"


@dataclass(frozen=True)
class Bar:
    itinerary_id: Any
    depart_text: str
    arrive_text: str  # "HH:MM" in the arrival offset, with " +N" for a later local day
    parts: list = field(default_factory=list)


@dataclass(frozen=True)
class TimelineDay:
    day: str
    start_min: int  # minutes after the local midnight of the day, a whole hour
    end_min: int
    bars: list = field(default_factory=list)


def _local(t: datetime, offset_min: int) -> datetime:
    """As `local()` of `app/web/pages.py` (no import: pages imports this module)."""
    return t.astimezone(timezone(timedelta(minutes=offset_min)))


def _minutes(t: datetime, base: datetime) -> float:
    return (t - base).total_seconds() / 60


def timeline(rows: Sequence[tuple], day_of: Callable[[Any], str | None]) -> list[TimelineDay]:
    """One TimelineDay per departure day (date order); `rows` are (itinerary, fare, cost) tuples."""
    spans: dict[str, list] = {}
    for row in rows:
        it = row[0]
        if not it.legs:
            continue
        key = day_of(it)
        if key is None:
            continue
        legs = list(it.legs)
        first = legs[0]
        depart = _local(first.depart_at, first.depart_offset_min)
        midnight = depart.replace(hour=0, minute=0, second=0, microsecond=0)
        points = [(leg, _minutes(leg.depart_at, midnight), _minutes(leg.arrive_at, midnight)) for leg in legs]
        spans.setdefault(key, []).append((it, depart, points))
    result = []
    for key in sorted(spans):
        entries = spans[key]
        lo = min(p[0][1] for _, _, p in entries)
        hi = max(p[-1][2] for _, _, p in entries)
        start = int(lo // 60) * 60
        end = -(-int(hi) // 60) * 60
        if end - start < MIN_AXIS_MIN:
            start = max(0, end - MIN_AXIS_MIN)
            end = max(end, start + MIN_AXIS_MIN)
        size = end - start

        def pct(m: float) -> float:
            return round((m - start) * 100 / size, 3)

        bars = []
        for it, depart, points in entries:
            parts: list = []
            for i, (leg, a, b) in enumerate(points):
                if i:
                    prev_end = points[i - 1][2]
                    if a > prev_end:
                        parts.append(GapPart(leg.from_name, round(a - prev_end), pct(prev_end), pct(a) - pct(prev_end)))
                parts.append(LegPart(leg.mode, pct(a), pct(b) - pct(a)))
            last = points[-1][0]
            arrive = _local(last.arrive_at, last.arrive_offset_min)
            gap = (arrive.date() - depart.date()).days
            arrive_text = arrive.strftime("%H:%M") + (f" +{gap}" if gap > 0 else "")
            bars.append(Bar(it.id, depart.strftime("%H:%M"), arrive_text, parts))
        result.append(TimelineDay(key, start, end, bars))
    return result
