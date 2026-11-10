"""The door-to-door minutes of an itinerary (#1855): travel, access, egress and airport time."""

from types import SimpleNamespace

from app.door import FLIGHT, door_minutes
from app.ranking import Weights


def _it(start, end, duration, mode="train"):
    legs = [SimpleNamespace(from_name=start, to_name="x", mode=mode),
            SimpleNamespace(from_name="x", to_name=end, mode=mode)]
    return SimpleNamespace(legs=legs, duration_min=duration)


def _p(id, text, kind, minutes):
    return SimpleNamespace(id=id, place_text=text, kind=kind, minutes=minutes, cost=0)


def test_train_with_access_and_egress_minutes():
    places = [_p(1, "A", "access", 35), _p(2, "B", "egress", 15)]
    assert door_minutes(_it("A", "B", 300), places, Weights()) == 350


def test_flight_adds_default_airport_times():
    it = _it("A", "B", 90, mode=FLIGHT)
    assert door_minutes(it, [], Weights()) == 240


def test_no_legs_or_no_matching_place_gives_duration():
    assert door_minutes(SimpleNamespace(legs=[], duration_min=75), [], Weights()) == 75
    assert door_minutes(_it("A", "B", 300), [_p(1, "C", "access", 35)], Weights()) == 300
