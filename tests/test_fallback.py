"""Transfers without a later captured connection (#1772)."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.fallback import build_index, no_fallback


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 10, hour, minute, tzinfo=timezone.utc)


def leg(frm, to, depart, arrive, from_code=None, to_code=None):
    return SimpleNamespace(from_name=frm, to_name=to, from_code=from_code, to_code=to_code,
                           depart_at=depart, arrive_at=arrive)


def itinerary(*legs):
    return SimpleNamespace(legs=list(legs))


def a_to_x_to_b():
    """A -> X (arrives 19:00), then X -> B (departs 21:00)."""
    return itinerary(leg("A", "X", at(18), at(19)), leg("X", "B", at(21), at(23)))


def test_no_other_itinerary_gives_the_transfer():
    it = a_to_x_to_b()
    assert no_fallback(it, build_index([it])) == [0]


def test_later_connection_from_x_to_b_removes_the_transfer():
    it = a_to_x_to_b()
    other = itinerary(leg("X", "B", at(22), at(23, 30)))
    assert no_fallback(it, build_index([it, other])) == []


def test_departure_at_the_same_time_is_no_later_connection():
    it = a_to_x_to_b()
    other = itinerary(leg("X", "B", at(21), at(23)))
    assert no_fallback(it, build_index([it, other])) == [0]


def test_other_final_station_is_no_later_connection():
    it = a_to_x_to_b()
    other = itinerary(leg("X", "C", at(22), at(23, 30)))
    assert no_fallback(it, build_index([it, other])) == [0]


def test_earlier_departure_is_no_later_connection():
    it = a_to_x_to_b()
    other = itinerary(leg("X", "B", at(20), at(22)))
    assert no_fallback(it, build_index([it, other])) == [0]


def test_station_matches_by_code():
    it = itinerary(leg("Alpha", "Xray", at(18), at(19), to_code="XRY"),
                   leg("Xray", "Bravo", at(21), at(23), from_code="XRY", to_code="BRV"))
    other = itinerary(leg("Xray Central", "Bravo", at(22), at(23, 30), from_code="XRY", to_code="BRV"))
    assert no_fallback(it, build_index([it, other])) == []


def test_different_code_is_no_later_connection_even_with_the_same_name():
    it = itinerary(leg("Alpha", "Xray", at(18), at(19), to_code="XRY"),
                   leg("Xray", "Bravo", at(21), at(23), from_code="XRY", to_code="BRV"))
    other = itinerary(leg("Xray", "Bravo", at(22), at(23, 30), from_code="XRZ", to_code="BRV"))
    assert no_fallback(it, build_index([it, other])) == [0]


def test_station_matches_by_name_without_codes_and_other_case():
    it = itinerary(leg("A", "Xray  Station", at(18), at(19)), leg("X", "B", at(21), at(23)))
    other = itinerary(leg("xray station", "b", at(22), at(23, 30)))
    assert no_fallback(it, build_index([it, other])) == []


def test_the_itinerary_is_never_its_own_later_connection():
    it = itinerary(leg("A", "X", at(18), at(19)), leg("X", "B", at(21), at(23)),
                   leg("B", "X", at(23, 30), at(23, 50)), leg("X", "B", at(23, 55), at(0, 10)))
    # Transfer 0 would have the own leg X -> B at 23:55 as its later connection: it still counts as none.
    assert no_fallback(it, build_index([it])) == [0, 1, 2]


def test_an_itinerary_with_one_leg_gives_nothing():
    it = itinerary(leg("A", "B", at(18), at(19)))
    assert no_fallback(it, build_index([it])) == []
