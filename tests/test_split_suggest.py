"""The transfer places of the itineraries of a trip (#1458)."""

from types import SimpleNamespace

from app.split_suggest import via_places


def leg(seq, to_name):
    return SimpleNamespace(seq=seq, to_name=to_name)


def itin(*names):
    """An itinerary whose legs end at each name in order."""
    return SimpleNamespace(legs=[leg(i, name) for i, name in enumerate(names)])


def test_counts_most_frequent_first():
    itineraries = [
        itin("Köln Hbf", "Berlin Hbf"),
        itin("Köln Hbf", "Berlin Hbf"),
        itin("Köln Hbf", "Berlin Hbf"),
        itin("Frankfurt(Main)Hbf", "Berlin Hbf"),
        itin("Frankfurt(Main)Hbf", "Berlin Hbf"),
        itin("Berlin Hbf"),
    ]
    assert via_places(itineraries, skip=[]) == [("Köln Hbf", 3), ("Frankfurt(Main)Hbf", 2)]


def test_casefold_same_place_and_first_spelling():
    itineraries = [
        itin("köln hbf", "Berlin Hbf"),
        itin("Köln Hbf", "Berlin Hbf"),
    ]
    assert via_places(itineraries, skip=[]) == [("köln hbf", 2)]


def test_place_on_two_legs_counts_once():
    itineraries = [
        itin("Köln Hbf", "Köln Hbf ", "Berlin Hbf"),
        itin("Berlin Hbf"),
    ]
    assert via_places(itineraries, skip=[]) == [("Köln Hbf", 1)]


def test_last_leg_is_not_a_transfer():
    assert via_places([itin("Berlin Hbf")], skip=[]) == []


def test_legs_are_read_in_seq_order():
    it = SimpleNamespace(legs=[leg(2, "Berlin Hbf"), leg(0, "Köln Hbf"), leg(1, "Hamm")])
    assert via_places([it], skip=[]) == [("Hamm", 1), ("Köln Hbf", 1)]


def test_skip_hides_names_case_insensitive():
    itineraries = [
        itin("Köln Hbf", "Berlin Hbf"),
        itin("Frankfurt(Main)Hbf", "Berlin Hbf"),
    ]
    assert via_places(itineraries, skip=["KÖLN HBF", "Origin"]) == [("Frankfurt(Main)Hbf", 1)]


def test_limit():
    itineraries = [itin(f"Place {i}", "End") for i in range(8)]
    assert len(via_places(itineraries, skip=[], limit=5)) == 5
    assert len(via_places(itineraries, skip=[], limit=3)) == 3


def test_tie_is_ordered_a_to_z():
    itineraries = [
        itin("Zwolle", "End"),
        itin("Aachen", "End"),
        itin("Mainz", "End"),
    ]
    assert via_places(itineraries, skip=[]) == [("Aachen", 1), ("Mainz", 1), ("Zwolle", 1)]


def test_empty_names_are_ignored():
    assert via_places([itin("  ", "End")], skip=[]) == []
