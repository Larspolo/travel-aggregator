"""Range of hour values in which the best offer stays the best (#1935)."""

from decimal import Decimal

from app.tradeoff import best_range

D = Decimal
H = D("20")
A = (D("120"), D("121"))  # a: slope 1
NEAR_BELOW = (D("140"), D("143"))  # slope 3, break-even 10, better below
FAR_BELOW = (D("125"), D("128"))  # slope 3, break-even 17.5, better below
FIRST_ABOVE = (D("135"), D("135"))  # slope 0, break-even 35, better above
SECOND_ABOVE = (D("145"), D("145"))  # slope 0, break-even 45, better above


def test_one_offer_better_below_gives_lower_limit_only() -> None:
    assert best_range(*A, [NEAR_BELOW], H) == (D("10.00"), None)


def test_one_below_and_one_above_give_both_limits() -> None:
    assert best_range(*A, [NEAR_BELOW, FIRST_ABOVE], H) == (D("10.00"), D("35.00"))


def test_no_other_offers_give_no_limits() -> None:
    assert best_range(*A, [], H) == (None, None)


def test_same_slope_gives_no_limits() -> None:
    assert best_range(*A, [(D("130"), D("131"))], H) == (None, None)


def test_infinite_total_gives_no_limits() -> None:
    assert best_range(*A, [(D("Infinity"), D("Infinity"))], H) == (None, None)


def test_lower_limit_is_the_highest_break_even_below() -> None:
    assert best_range(*A, [NEAR_BELOW, FAR_BELOW], H) == (D("17.50"), None)


def test_upper_limit_is_the_lowest_break_even_above() -> None:
    assert best_range(*A, [SECOND_ABOVE, FIRST_ABOVE], H) == (None, D("35.00"))
