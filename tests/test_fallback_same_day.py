"""A later connection counts only when it arrives on the same local day (#1794)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.fallback import build_index, no_fallback


def at(day: int, hour: int) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


def leg(frm, to, depart, arrive, offset=0):
    return SimpleNamespace(from_name=frm, to_name=to, from_code=None, to_code=None, depart_at=depart,
                           arrive_at=arrive, arrive_offset_min=offset)


def itinerary(*legs):
    return SimpleNamespace(legs=list(legs))


def a_to_x_to_b():
    """A -> X, then X -> B: departs 21:00, arrives 22:00 UTC on 10 November."""
    return itinerary(leg("A", "X", at(10, 18), at(10, 19)), leg("X", "B", at(10, 21), at(10, 22)))


def test_a_connection_of_the_next_day_does_not_remove_the_transfer():
    it = a_to_x_to_b()
    other = itinerary(leg("X", "B", at(11, 7), at(11, 8)))
    assert no_fallback(it, build_index([it, other])) == [0]


def test_a_connection_of_the_same_day_removes_the_transfer():
    it = a_to_x_to_b()
    other = itinerary(leg("X", "B", at(10, 22), at(10, 23)))
    assert no_fallback(it, build_index([it, other])) == []


def test_the_day_is_the_local_day_of_the_offset():
    """At +60 min, 22:00 UTC is 23:00 local and 23:30 UTC is 00:30 local of the next day."""
    it = itinerary(leg("A", "X", at(10, 18), at(10, 19), 60), leg("X", "B", at(10, 21), at(10, 22), 60))
    other = itinerary(leg("X", "B", at(10, 22), at(10, 22) + timedelta(minutes=90), 60))
    assert no_fallback(it, build_index([it, other])) == [0]
