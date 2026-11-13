"""An itinerary matches a via place when it stops at or changes at the place (epic #2699)."""

from types import SimpleNamespace

from app.tripmatch import passes_via


def _leg(frm, to, stops=()):
    return SimpleNamespace(from_name=frm, to_name=to, stops=[SimpleNamespace(name=s) for s in stops])


def _it(*legs):
    return SimpleNamespace(legs=list(legs))


def test_a_stop_of_a_direct_leg_matches_by_part_of_its_name():
    it = _it(_leg("Amsterdam Centraal", "Berlin Hbf", stops=["Hannover Hbf"]))
    assert passes_via(it, "hannover")
    assert passes_via(it, "Hannover Hbf")


def test_a_change_place_of_two_legs_matches():
    it = _it(_leg("Amsterdam Centraal", "Hannover Hbf"), _leg("Hannover Hbf", "Berlin Hbf"))
    assert passes_via(it, "Hannover")


def test_a_stop_name_with_diacritics_matches_without_them():
    it = _it(_leg("Milano Centrale", "Basel SBB", stops=["Zürich HB"]))
    assert passes_via(it, "zurich")


def test_a_direct_leg_with_no_stops_does_not_match_a_city_between_or_the_ends():
    it = _it(_leg("Amsterdam Centraal", "Berlin Hbf"))
    assert not passes_via(it, "Hannover")
    assert not passes_via(it, "Amsterdam")
    assert not passes_via(it, "Berlin")


def test_an_empty_or_blank_text_matches_each_itinerary():
    it = _it(_leg("Amsterdam Centraal", "Berlin Hbf"))
    assert passes_via(it, "")
    assert passes_via(it, "   ")
