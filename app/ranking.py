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
    extras: tuple[tuple[str, Decimal], ...] = ()


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_EVEN)


def effective_cost(
    price: Decimal,
    duration_min: int,
    transfers: int,
    weights: Weights,
    extras: tuple[tuple[str, Decimal], ...] = (),
) -> Breakdown:
    """Give the effective cost of one fare and its parts.

    An extra is a (label, amount) part. An amount may be negative (a bonus).
    """
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
    extra_parts = tuple((label, _cents(Decimal(amount))) for label, amount in extras)
    total = price_part + time_part + transfer_part + sum((amount for _, amount in extra_parts), Decimal("0"))
    return Breakdown(price_part, time_part, transfer_part, total, extra_parts)


def _amount(value: Decimal) -> str:
    """Whole euros without decimals, otherwise two cent digits."""
    if value == value.to_integral_value():
        return f"€{int(value)}"
    return f"€{value:.2f}"


def format_breakdown(b: Breakdown) -> str:
    """Give the breakdown as short plain text, e.g. '€90 price + €62 time + €30 transfers = €182'.

    A part that is 0 is left out. The text is plain: the template escapes it (P5).
    """
    labels = (("price", b.price), ("time", b.time_cost), ("transfers", b.transfer_cost)) + b.extras
    parts = [f"{_amount(value)} {label}" for label, value in labels if value != 0]
    if not parts:
        return _amount(b.total)
    return f"{' + '.join(parts)} = {_amount(b.total)}"
