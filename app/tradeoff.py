"""Break-even hour value of two offers (epic #892)."""

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from app.ranking import CENT


@dataclass(frozen=True)
class BreakEven:
    """The hour value at which two offers cost the same.

    `better` is the side of `hour_value` on which the other offer x costs less than a:
    "above" or "below".
    """

    hour_value: Decimal  # EUR per hour, rounded to cents
    better: str  # "above" or "below"


def break_even(
    a_now: Decimal,
    a_next: Decimal,
    x_now: Decimal,
    x_next: Decimal,
    h: Decimal,
) -> BreakEven | None:
    """Give the hour value at which offers a and x have the same effective cost.

    Each total is given at the hour value `h` (`*_now`) and at `h + 1` (`*_next`).
    The effective cost is linear in the hour value, so the slope is the second total minus the first.
    Give None when no hour value changes the order, when the value is below 0,
    or when an offer has an infinite total (no rate, #385).
    """
    totals = (a_now, a_next, x_now, x_next)
    if any(not t.is_finite() for t in totals):
        return None

    slope_a = a_next - a_now
    slope_x = x_next - x_now
    if slope_a == slope_x:
        return None

    raw = h + (x_now - a_now) / (slope_a - slope_x)
    if raw < 0:
        return None

    hour_value = raw.quantize(CENT, rounding=ROUND_HALF_EVEN)
    better = "above" if slope_x < slope_a else "below"
    return BreakEven(hour_value, better)
