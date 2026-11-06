"""Effective cost of one fare (docs/SPEC.md, section 7.1)."""

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Weights:
    """The markups of the active profile, in EUR."""

    hour_markup: Decimal = Decimal("15")
    transfer_markup: Decimal = Decimal("10")


@dataclass(frozen=True)
class Breakdown:
    """The parts of the effective cost. The total is the sum of the rounded parts."""

    price: Decimal
    time_cost: Decimal
    transfer_cost: Decimal
    total: Decimal


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_EVEN)


def effective_cost(price: Decimal, duration_min: int, transfers: int, weights: Weights) -> Breakdown:
    """Give the effective cost of one fare and its parts."""
    values = {
        "price": price,
        "duration_min": duration_min,
        "transfers": transfers,
        "hour_markup": weights.hour_markup,
        "transfer_markup": weights.transfer_markup,
    }
    for name, value in values.items():
        if value < 0:
            raise ValueError(f"{name} must not be negative: {value}")
    price_part = _cents(Decimal(price))
    time_part = _cents(Decimal(duration_min) * weights.hour_markup / 60)  # multiply first: exact halves
    transfer_part = _cents(Decimal(transfers) * weights.transfer_markup)
    return Breakdown(price_part, time_part, transfer_part, price_part + time_part + transfer_part)


def _amount(value: Decimal) -> str:
    """Whole euros without decimals, otherwise two cent digits."""
    if value == value.to_integral_value():
        return f"€{int(value)}"
    return f"€{value:.2f}"


def format_breakdown(b: Breakdown) -> str:
    """Give the breakdown as short plain text, e.g. '€90 price + €62 time + €30 transfers = €182'.

    A part that is 0 is left out. The text is plain: the template escapes it (P5).
    """
    labels = (("price", b.price), ("time", b.time_cost), ("transfers", b.transfer_cost))
    parts = [f"{_amount(value)} {label}" for label, value in labels if value != 0]
    if not parts:
        return _amount(b.total)
    return f"{' + '.join(parts)} = {_amount(b.total)}"
