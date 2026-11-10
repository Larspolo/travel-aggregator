"""Tests of the hour values at which each booking was the best offer (#1709)."""

from decimal import Decimal

from app.calibrate import best_fit, booking_interval

D = Decimal
H = D("10")
INF = D("Infinity")


def totals(price: str, hours: str) -> tuple[Decimal, Decimal]:
    """The totals of an offer at the hour value H and H + 1: price + hour value × hours."""
    p, t = D(price), D(hours)
    return p + H * t, p + (H + 1) * t


def test_faster_dearer_booking_needs_a_low_limit() -> None:
    # 20 EUR more for 1 hour less than the only other offer.
    assert booking_interval(totals("120", "2"), [totals("100", "3")], H) == (D("20.00"), None)


def test_slower_cheaper_booking_needs_a_high_limit() -> None:
    # 1 hour more for 40 EUR less.
    assert booking_interval(totals("60", "4"), [totals("100", "3")], H) == (None, D("40.00"))


def test_best_fit_of_the_two() -> None:
    fast = booking_interval(totals("120", "2"), [totals("100", "3")], H)
    slow = booking_interval(totals("60", "4"), [totals("100", "3")], H)
    assert best_fit([fast, slow]) == (D("20.00"), D("40.00"), 2, 2)


def test_dearer_and_slower_booking_has_no_interval() -> None:
    assert booking_interval(totals("120", "4"), [totals("100", "3")], H) is None
    fast = (D("20.00"), None)
    assert best_fit([fast, None]) == (D("20.00"), None, 1, 2)


def test_intervals_with_no_common_value_give_the_lower_one() -> None:
    assert best_fit([(D("50"), D("60")), (D("10"), D("20"))]) == (D("10"), D("20"), 1, 2)


def test_both_limits_and_no_overlap() -> None:
    # The booked offer is better between 20 and 60 EUR per hour.
    others = [totals("100", "3"), totals("180", "1")]
    assert booking_interval(totals("120", "2"), others, H) == (D("20.00"), D("60.00"))
    # A low limit above the high limit gives no interval.
    assert booking_interval(totals("120", "2"), [totals("100", "3"), totals("130", "1")], H) is None


def test_same_slope_compares_the_totals() -> None:
    same_time = totals("100", "3")
    assert booking_interval(totals("90", "3"), [same_time], H) == (None, None)
    assert booking_interval(totals("100", "3"), [same_time], H) == (None, None)
    assert booking_interval(totals("110", "3"), [same_time], H) is None


def test_break_even_below_zero_compares_the_totals() -> None:
    # The other offer is cheaper and faster: break_even() is None or the booking loses.
    assert booking_interval(totals("200", "3"), [totals("100", "2")], H) is None


def test_infinite_other_total_gives_no_limit() -> None:
    assert booking_interval(totals("120", "2"), [(INF, INF)], H) == (None, None)


def test_infinite_booked_total_loses_to_a_finite_offer() -> None:
    assert booking_interval((INF, INF), [totals("100", "3")], H) is None


def test_best_fit_with_no_interval() -> None:
    assert best_fit([]) is None
    assert best_fit([None, None]) is None


def test_best_fit_touching_ends_share_a_value() -> None:
    assert best_fit([(D("10"), D("20")), (D("20"), D("30"))]) == (D("20"), D("20"), 2, 2)


def test_best_fit_more_intervals_win_over_a_lower_low_end() -> None:
    ivs = [(None, D("5")), (D("10"), D("30")), (D("15"), None), (D("12"), D("18"))]
    assert best_fit(ivs) == (D("15"), D("18"), 3, 4)
