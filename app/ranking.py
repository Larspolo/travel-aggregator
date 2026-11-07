"""Effective cost of one fare (docs/SPEC.md, section 7.1)."""

from dataclasses import dataclass, replace
from datetime import time
from decimal import ROUND_HALF_EVEN, Decimal

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Weights:
    """The markups of the active profile, in EUR."""

    hour_markup: Decimal = Decimal("15")
    transfer_markup: Decimal = Decimal("10")
    # The "Advanced" values (P2) of a flight (#99); 0 disables each.
    airport_before_min: int = 120
    airport_after_min: int = 30
    baggage_fee: Decimal = Decimal("0")
    # The time-of-day penalty (#141): local times; a penalty of 0 disables it.
    early_limit: time = time(6, 0)
    late_limit: time = time(23, 30)
    time_window_penalty: Decimal = Decimal("0")
    # The night travel adjustment (#142): a signed amount (negative = bonus); 0 disables it.
    night_start: time = time(23, 0)
    night_end: time = time(6, 0)
    night_min: int = 240
    night_adjust: Decimal = Decimal("0")
    # The hour markup inside the night window (#143); None = the same as hour_markup.
    night_hour_markup: Decimal | None = None
    # The short-transfer penalty (#173): a transfer shorter than the minimum; a penalty of 0 disables it.
    short_transfer_min: int = 10
    short_transfer_penalty: Decimal = Decimal("0")
    # The mode markups (#174): a flat amount per itinerary that uses the mode; a negative amount is a discount.
    train_markup: Decimal = Decimal("0")
    bus_markup: Decimal = Decimal("0")
    flight_markup: Decimal = Decimal("0")
    ferry_markup: Decimal = Decimal("0")
    # The flexibility amounts per tier (#175): signed (negative = bonus); 0 disables each.
    flex_non_refundable: Decimal = Decimal("0")
    flex_partly_refundable: Decimal = Decimal("0")
    flex_flexible: Decimal = Decimal("0")
    # The penalty per self-transfer of a fare (#176); 0 disables it.
    self_transfer_penalty: Decimal = Decimal("0")
    # The age in hours after which a row is stale (#275): a display flag only, not part of the cost.
    stale_hours: int = 24
    # The penalty of a stale row (#276): added to its cost; 0 disables it.
    stale_penalty: Decimal = Decimal("0")


@dataclass(frozen=True)
class Breakdown:
    """The parts of the effective cost. The total is the sum of the rounded parts."""

    price: Decimal
    time_cost: Decimal
    transfer_cost: Decimal
    total: Decimal
    extras: tuple[tuple[str, Decimal], ...] = ()
    original: str = ""  # the price in its own currency when it is not EUR, e.g. "CHF 120" (#385)
    no_rate: str = ""  # the currency code when it has no rate: then the price and the total are Infinity (#385)


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


def _amount(value: Decimal, symbol: str = "€") -> str:
    """Whole euros without decimals, otherwise two cent digits."""
    if value == value.to_integral_value():
        return f"{symbol}{int(value)}"
    return f"{symbol}{value:.2f}"


def in_eur(b: Breakdown, amount: Decimal, currency: str, eur: Decimal | None) -> Breakdown:
    """The breakdown of a fare whose price is not in EUR (#385): `b` was computed with the EUR value `eur`.
    With no rate (`eur` None) the total is Infinity, so that the row sorts after the rows with a cost."""
    if currency == "EUR":
        return b
    if eur is None:
        inf = Decimal("Infinity")
        return Breakdown(price=inf, time_cost=b.time_cost, transfer_cost=b.transfer_cost, total=inf,
                         extras=b.extras, no_rate=currency)
    return replace(b, original=_amount(amount, f"{currency} "))


def bar_parts(b: Breakdown) -> list[tuple[str, Decimal, Decimal]]:
    """Give the positive parts of the breakdown as (label, x, width), in percent of their sum, for the cost bar (#590).

    No parts when the price has no rate or the sum is 0.
    """
    if b.no_rate:
        return []
    labels = (("price", b.price), ("time", b.time_cost), ("transfers", b.transfer_cost)) + b.extras
    positive = [(label, value) for label, value in labels if value > 0]
    total = sum((value for _, value in positive), Decimal(0))
    parts, x = [], Decimal(0)
    for label, value in positive if total else []:
        width = (value * 100 / total).quantize(Decimal("0.1"))
        parts.append((label, x, width))
        x += width
    return parts


def format_total(b: Breakdown) -> str:
    """Give the effective cost alone, e.g. '€182' (#590)."""
    return "no rate" if b.no_rate else _amount(b.total)


def format_breakdown(b: Breakdown) -> str:
    """Give the breakdown as short plain text, e.g. '€90 price + €62 time + €30 transfers = €182'.

    A part that is 0 is left out. The text is plain: the template escapes it (P5).
    """
    if b.no_rate:
        return f"no rate for {b.no_rate}"
    price_label = f"{b.original} ({_amount(b.price)}) price" if b.original else None
    labels = (("price", b.price), ("time", b.time_cost), ("transfers", b.transfer_cost)) + b.extras
    parts = [price_label if label == "price" and price_label else f"{_amount(value)} {label}"
             for label, value in labels if value != 0]
    if not parts:
        return _amount(b.total)
    return f"{' + '.join(parts)} = {_amount(b.total)}"
