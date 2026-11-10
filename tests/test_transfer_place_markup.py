"""The transfer place markup: a flat amount for each transfer at a marked place, a discount when negative (#1850)."""

from decimal import Decimal
from types import SimpleNamespace

from app.profiles import from_config, to_config
from app.ranking import Weights
from app.risk import transfer_place_extras


def _leg(from_name, to_name):
    return SimpleNamespace(from_name=from_name, to_name=to_name)


def _it(*stations):
    """An itinerary of one leg per pair of stations: (from, to), (from, to), ..."""
    return SimpleNamespace(legs=[_leg(a, b) for a, b in stations])


def _brussels(name="Brussels-Midi", markup=Decimal("20")):
    return Weights(transfer_place1_name=name, transfer_place1_markup=markup)


def test_a_transfer_at_a_marked_place_adds_its_part():
    it = _it(("Amsterdam", "Brussels-Midi/Brussel-Zuid"), ("Brussel-Zuid", "Paris-Nord"))
    assert transfer_place_extras(it, _brussels()) == (("transfer at Brussels-Midi", Decimal("20")),)


def test_the_name_matches_without_case_and_outer_spaces():
    it = _it(("Amsterdam", "Brussels-Midi/Brussel-Zuid"), ("Brussel-Zuid", "Paris-Nord"))
    assert transfer_place_extras(it, _brussels(" brussels-midi ")) == (
        ("transfer at brussels-midi", Decimal("20")),)


def test_the_departure_station_of_the_next_leg_also_matches():
    it = _it(("Amsterdam", "Lille"), ("Brussels-Midi", "Paris-Nord"))
    assert transfer_place_extras(it, _brussels()) == (("transfer at Brussels-Midi", Decimal("20")),)


def test_a_direct_itinerary_gets_no_part():
    it = _it(("Amsterdam", "Brussels-Midi"))
    assert transfer_place_extras(it, _brussels()) == ()


def test_the_first_departure_and_the_last_arrival_are_no_transfer():
    it = _it(("Brussels-Midi", "Lille"), ("Lille", "Paris-Nord"))
    assert transfer_place_extras(it, _brussels()) == ()
    it = _it(("Amsterdam", "Lille"), ("Lille", "Brussels-Midi"))
    assert transfer_place_extras(it, _brussels()) == ()


def test_two_transfers_at_one_place_add_the_amount_two_times():
    it = _it(("Amsterdam", "Brussels-Midi"), ("Brussels-Midi", "Lille"), ("Lille", "Brussels-Midi"),
             ("Brussels-Midi", "Paris-Nord"))
    assert transfer_place_extras(it, _brussels()) == (
        ("transfer at Brussels-Midi", Decimal("20")), ("transfer at Brussels-Midi", Decimal("20")))


def test_a_negative_markup_is_a_discount():
    it = _it(("Amsterdam", "Brussels-Midi/Brussel-Zuid"), ("Brussel-Zuid", "Paris-Nord"))
    assert transfer_place_extras(it, _brussels(markup=Decimal("-10"))) == (
        ("transfer at Brussels-Midi", Decimal("-10")),)


def test_an_empty_name_or_a_markup_of_zero_adds_no_part():
    it = _it(("Amsterdam", "Brussels-Midi/Brussel-Zuid"), ("Brussel-Zuid", "Paris-Nord"))
    assert transfer_place_extras(it, _brussels(name="")) == ()
    assert transfer_place_extras(it, _brussels(markup=Decimal("0"))) == ()
    assert transfer_place_extras(it, Weights()) == ()


def test_each_of_the_three_slots_adds_its_own_part():
    it = _it(("Amsterdam", "Brussels-Midi"), ("Brussels-Midi", "Lille"), ("Lille", "Paris-Nord"))
    w = Weights(transfer_place1_name="Brussels-Midi", transfer_place1_markup=Decimal("20"),
                transfer_place2_name="Lille", transfer_place2_markup=Decimal("-4"),
                transfer_place3_name="Paris-Nord", transfer_place3_markup=Decimal("6"))
    assert transfer_place_extras(it, w) == (
        ("transfer at Brussels-Midi", Decimal("20")), ("transfer at Lille", Decimal("-4")))


def test_a_saved_profile_with_the_transfer_place_slots_loads_the_same_weights():
    w = Weights(transfer_place1_name="Brussels-Midi", transfer_place1_markup=Decimal("20"),
                transfer_place2_name="Lille", transfer_place2_markup=Decimal("-4"))
    assert from_config(to_config(w)) == w
    assert from_config(to_config(Weights())) == Weights()
