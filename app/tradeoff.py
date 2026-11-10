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


def best_range(
    a_now: Decimal,
    a_next: Decimal,
    others: list[tuple[Decimal, Decimal]],
    h: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    """Give the hour values between which offer a stays the best.

    `others` holds `(x_now, x_next)` for each other offer. The lower limit is the highest
    break-even where that offer is better below it; the upper limit is the lowest break-even
    where that offer is better above it. A limit is None when no offer sets it.
    """
    lower: Decimal | None = None
    upper: Decimal | None = None
    for x_now, x_next in others:
        result = break_even(a_now, a_next, x_now, x_next, h)
        if result is None:
            continue
        if result.better == "below":
            if lower is None or result.hour_value > lower:
                lower = result.hour_value
        elif upper is None or result.hour_value < upper:
            upper = result.hour_value
    return lower, upper


def best_at_price(best_total: Decimal, price: Decimal, total: Decimal) -> Decimal | None:
    """Give the price at which an offer has the same effective cost as the best offer.

    `total` is the effective cost of the offer at `price`; lowering the price by the
    difference to `best_total` makes it as cheap as the best. Give None when a value is
    not finite (no rate, #385) or when the price would be 0 or less.
    """
    if not all(t.is_finite() for t in (best_total, price, total)):
        return None
    result = price - (total - best_total)
    if result <= 0:
        return None
    return result
