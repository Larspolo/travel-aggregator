"""Derived values of an itinerary, computed at ingest (ticket #29).

The score reads these values at query time, so they are stored with the offer.
All times must be timezone-aware: durations use UTC instants, so a change of
offset (daylight saving, a border) between legs is handled correctly.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence


@dataclass(frozen=True)
class Leg:
    """One leg of a trip: a train, bus or flight between two times."""

    depart_at: datetime
    arrive_at: datetime
    mode: str


@dataclass(frozen=True)
class Derived:
    """The values of an itinerary that ranking reads directly."""

    duration_min: int
    transfers: int
    min_transfer_min: int | None
    mode_summary: str


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"naive datetime: {value!r}; all times must be timezone-aware")


def _minutes(delta) -> int:
    return int(delta.total_seconds() // 60)


def derive(legs: Sequence[Leg]) -> Derived:
    """Compute duration, transfers, the shortest transfer and the mode summary of legs.

    Raises ValueError for an empty list or for a naive datetime.
    """
    if not legs:
        raise ValueError("an itinerary needs at least one leg")
    for leg in legs:
        _require_aware(leg.depart_at)
        _require_aware(leg.arrive_at)

    # Convert to UTC first: subtracting two datetimes that share one tzinfo
    # object uses the wall clock and ignores a DST change between them.
    departs = [leg.depart_at.astimezone(timezone.utc) for leg in legs]
    arrives = [leg.arrive_at.astimezone(timezone.utc) for leg in legs]

    duration_min = _minutes(arrives[-1] - departs[0])

    gaps = [
        _minutes(departs[i + 1] - arrives[i])
        for i in range(len(legs) - 1)
    ]
    min_transfer_min = min(gaps) if gaps else None

    modes: list[str] = []
    for leg in legs:
        if not modes or modes[-1] != leg.mode:
            modes.append(leg.mode)

    return Derived(
        duration_min=duration_min,
        transfers=len(legs) - 1,
        min_transfer_min=min_transfer_min,
        mode_summary="+".join(modes),
    )
