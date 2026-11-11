"""The carrier markup or discount: a flat amount for each marked carrier an itinerary uses, once per itinerary (#1530)."""

from decimal import Decimal
from types import SimpleNamespace

from app.profiles import from_config, to_config
from app.ranking import Weights, effective_cost
from app.risk import carrier_extras


def _it(*carriers):
    return SimpleNamespace(legs=[SimpleNamespace(carrier=c) for c in carriers])


def test_a_carrier_markup_adds_one_part_for_a_leg_of_that_carrier():
    w = Weights(carrier1_name="Ryanair", carrier1_markup=Decimal("15"))
    assert carrier_extras(_it("Ryanair"), w) == (("carrier Ryanair", Decimal("15")),)
    assert carrier_extras(_it("KLM", "Ryanair"), w) == (("carrier Ryanair", Decimal("15")),)
    assert carrier_extras(_it("KLM"), w) == ()


def test_two_legs_of_one_carrier_give_one_part():
    w = Weights(carrier1_name="Ryanair", carrier1_markup=Decimal("15"))
    assert carrier_extras(_it("Ryanair", "Ryanair"), w) == (("carrier Ryanair", Decimal("15")),)


def test_the_name_matches_without_case_and_outer_spaces():
    w = Weights(carrier1_name="Ryanair", carrier1_markup=Decimal("15"))
    assert carrier_extras(_it("ryanair "), w) == (("carrier Ryanair", Decimal("15")),)
    w = Weights(carrier1_name="  ryanair", carrier1_markup=Decimal("15"))
    assert carrier_extras(_it("RYANAIR"), w) == (("carrier ryanair", Decimal("15")),)


def test_a_negative_markup_is_a_discount_that_lowers_the_cost():
    w = Weights(carrier1_name="Ryanair", carrier1_markup=Decimal("-10"))
    extras = carrier_extras(_it("Ryanair"), w)
    assert extras == (("carrier Ryanair", Decimal("-10")),)
    assert effective_cost(Decimal("100"), 0, 0, w, extras).total == Decimal("90.00")


def test_an_empty_name_or_a_markup_of_zero_adds_no_part():
    assert carrier_extras(_it("Ryanair"), Weights(carrier1_name="", carrier1_markup=Decimal("15"))) == ()
    assert carrier_extras(_it("Ryanair"), Weights(carrier1_name="Ryanair", carrier1_markup=Decimal("0"))) == ()
    assert carrier_extras(_it("Ryanair"), Weights()) == ()


def test_each_of_the_three_slots_adds_its_own_part():
    w = Weights(carrier1_name="Ryanair", carrier1_markup=Decimal("15"),
                carrier2_name="KLM", carrier2_markup=Decimal("-5"),
                carrier3_name="Flixbus", carrier3_markup=Decimal("8"))
    assert carrier_extras(_it("KLM", "Ryanair", "Flixbus"), w) == (
        ("carrier Ryanair", Decimal("15")), ("carrier KLM", Decimal("-5")), ("carrier Flixbus", Decimal("8")))


def test_a_saved_profile_with_the_carrier_slots_loads_the_same_weights():
    w = Weights(carrier1_name="Ryanair", carrier1_markup=Decimal("15"),
                carrier2_name="KLM", carrier2_markup=Decimal("-5"))
    assert from_config(to_config(w)) == w
    assert from_config(to_config(Weights())) == Weights()
