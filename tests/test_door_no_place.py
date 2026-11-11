"""A line for a station with no access or egress place (#2052)."""

from decimal import Decimal
from types import SimpleNamespace

from app.door import door_extras

H = Decimal("15")


def _it(start, end):
    return SimpleNamespace(legs=[SimpleNamespace(from_name=start, to_name="x"),
                                 SimpleNamespace(from_name="x", to_name=end)])


def _p(id, text, kind, minutes, cost):
    return SimpleNamespace(id=id, place_text=text, kind=kind, minutes=minutes, cost=Decimal(cost))


def test_egress_no_match_gives_zero_line_and_match_gives_parts():
    places = [_p(1, "Zürich HB", "egress", 15, "4.50")]
    assert door_extras(_it("A", "Zürich HB"), places, H) == (
        ("egress time", Decimal("3.75")), ("egress cost", Decimal("4.50")))
    assert door_extras(_it("A", "Zürich Flughafen"), places, H) == (
        ("no egress place for Zürich Flughafen", Decimal(0)),)


def test_access_no_match_gives_zero_line():
    places = [_p(1, "Bern", "access", 10, "1")]
    assert door_extras(_it("Basel", "B"), places, H) == (("no access place for Basel", Decimal(0)),)


def test_no_place_of_the_kind_gives_no_line():
    # only access places: the last station gets no egress line
    assert door_extras(_it("A", "B"), [_p(1, "A", "access", 10, "1")], H) == (
        ("access time", Decimal("2.5")), ("access cost", Decimal("1")))
    # only egress places: the first station gets no access line
    assert door_extras(_it("A", "B"), [_p(1, "B", "egress", 10, "1")], H) == (
        ("egress time", Decimal("2.5")), ("egress cost", Decimal("1")))
    assert door_extras(_it("A", "B"), [], H) == ()


def test_no_legs_gives_nothing():
    places = [_p(1, "A", "access", 10, "1"), _p(2, "B", "egress", 10, "1")]
    assert door_extras(SimpleNamespace(legs=[]), places, H) == ()


def test_line_adds_no_cost():
    places = [_p(1, "A", "access", 10, "1"), _p(2, "Z", "egress", 10, "1")]
    extras = door_extras(_it("A", "Elsewhere"), places, H)
    assert extras == (
        ("access time", Decimal("2.5")), ("access cost", Decimal("1")),
        ("no egress place for Elsewhere", Decimal(0)))
    assert sum(v for _, v in extras) == Decimal("3.5")
