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
    # The night value of a berth (#1808): None = night_adjust.
    night_seat_adjust: Decimal | None = None
    night_couchette_adjust: Decimal | None = None
    night_sleeper_adjust: Decimal | None = None
    # The overnight stop (#1256): a transfer with at least overnight_min night minutes adds overnight_cost.
    overnight_min: int = 240
    overnight_cost: Decimal = Decimal("0")
    # The CO₂ part (#1416): € per kg of CO₂ (0 disables it), and kg of CO₂ per hour and traveler per mode.
    co2_price_kg: Decimal = Decimal("0")
    co2_train_kg_h: Decimal = Decimal("3")
    co2_bus_kg_h: Decimal = Decimal("2")
    co2_flight_kg_h: Decimal = Decimal("90")
    co2_ferry_kg_h: Decimal = Decimal("3")
    # The wait before the "arrive by" time of the trip (#1295): € per hour; 0 disables it.
    wait_hour_markup: Decimal = Decimal("0")
    # The wait before the "leave after" time of the trip (#2022): € per hour; 0 disables it.  # #2022
    leave_hour_markup: Decimal = Decimal("0")
    # The hour markup inside the night window (#143); None = the same as hour_markup.
    night_hour_markup: Decimal | None = None
    # The hour value per mode (#1567): € per hour of a leg of the mode; None = the hour markup (no part).
    train_hour_markup: Decimal | None = None  # (#1567)
    bus_hour_markup: Decimal | None = None  # (#1567)
    flight_hour_markup: Decimal | None = None  # (#1567)
    ferry_hour_markup: Decimal | None = None  # (#1567)
    # The short-transfer penalty (#173): a transfer shorter than the minimum; a penalty of 0 disables it.
    short_transfer_min: int = 10
    short_transfer_penalty: Decimal = Decimal("0")
    # The change of station (#1501): its own minimum (None = short_transfer_min) and a penalty per change; 0 disables it.
    station_change_min: int | None = None
    station_change_penalty: Decimal = Decimal("0")
    # A penalty per transfer with no later captured connection (#1773); 0 disables it and runs no query.
    no_fallback_penalty: Decimal = Decimal("0")
    # The mode markups (#174): a flat amount per itinerary that uses the mode; a negative amount is a discount.
    train_markup: Decimal = Decimal("0")
    bus_markup: Decimal = Decimal("0")
    flight_markup: Decimal = Decimal("0")
    ferry_markup: Decimal = Decimal("0")
    # The flexibility amounts per tier (#175): signed (negative = bonus); 0 disables each.
    flex_non_refundable: Decimal = Decimal("0")
    flex_partly_refundable: Decimal = Decimal("0")
    flex_flexible: Decimal = Decimal("0")
    # The 1st class amount per hour (#691): signed (negative = bonus); 0 disables it.
    first_class_hour: Decimal = Decimal("0")
    # The penalty per self-transfer of a fare (#176); 0 disables it.
    self_transfer_penalty: Decimal = Decimal("0")
    # The fee per leg with a mandatory reservation that the fare does not include (#1623); 0 disables it.
    reservation_fee: Decimal = Decimal("0")
    # The percent of the EUR price of a fare in another currency than EUR (#1993); 0 disables the part.
    currency_fee_pct: Decimal = Decimal("0")
    # The age in hours after which a row is stale (#275): a display flag only, not part of the cost.
    stale_hours: int = 24
    # The penalty of a stale row (#276): added to its cost; 0 disables it.
    stale_penalty: Decimal = Decimal("0")
    # The hour tiers (#1014, marginal like tax brackets): from `after_min` of an active tier, each minute costs the
    # markup of that tier; `hour_markup` is the rate before the first active tier. An `after_min` of 0 disables the
    # tier. The night part (#143) stays night minutes × (night_hour_markup − hour_markup) / 60.
    hour_tier1_after_min: int = 0
    hour_tier1_markup: Decimal = Decimal("0")
    hour_tier2_after_min: int = 0
    hour_tier2_markup: Decimal = Decimal("0")
    # The carrier markups (#1530): a leg whose carrier is the name of a slot adds the markup once per itinerary.
    # A markup of 0 or an empty name disables the slot.
    carrier1_name: str = ""
    carrier1_markup: Decimal = Decimal("0")
    carrier2_name: str = ""
    carrier2_markup: Decimal = Decimal("0")
    carrier3_name: str = ""
    carrier3_markup: Decimal = Decimal("0")
    # The transfer place markups (#1850): a transfer at a place whose name a slot has adds the markup once per transfer.
    # A markup of 0 or an empty name disables the slot.
    transfer_place1_name: str = ""
    transfer_place1_markup: Decimal = Decimal("0")
    transfer_place2_name: str = ""
    transfer_place2_markup: Decimal = Decimal("0")
    transfer_place3_name: str = ""
    transfer_place3_markup: Decimal = Decimal("0")


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
    group: str = ""  # the price of a capture for 2 or more travelers, e.g. "€180 for 2 travelers" (#767)


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_EVEN)


def time_cost_raw(duration_min: int, weights: Weights) -> Decimal:
    """The unrounded time cost: each minute at the rate of its band (#1014); with no tier, minutes × hour_markup / 60."""
    tiers = sorted((a, Decimal(m)) for a, m in ((weights.hour_tier1_after_min, weights.hour_tier1_markup),
                                                (weights.hour_tier2_after_min, weights.hour_tier2_markup)) if a > 0)
    bands = [(0, Decimal(weights.hour_markup))] + tiers
    total = Decimal("0")
    for i, (start, rate) in enumerate(bands):
        end = bands[i + 1][0] if i + 1 < len(bands) else None
        minutes = max(0, (duration_min if end is None else min(duration_min, end)) - start)
        total += Decimal(minutes) * rate
    return total / 60  # multiply first: exact halves


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
    time_part = _cents(time_cost_raw(duration_min, weights))
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


def per_traveler(price: Decimal, travelers: int | None) -> Decimal:
    """The price of one traveler (#767): a group price divided by its travelers; 1 or no count keeps the price.
    `effective_cost()` rounds it to cents."""
    return Decimal(price) / travelers if travelers is not None and travelers > 1 else price


def for_group(b: Breakdown, amount: Decimal, currency: str, travelers: int | None) -> Breakdown:
    """The breakdown of a group price (#767): `b` was computed with the price per traveler; the text keeps the price
    of the group in its own currency. 1 or no count, or no rate, gives `b` with no change."""
    if travelers is None or travelers < 2 or b.no_rate:
        return b
    shown = _amount(amount) if currency == "EUR" else _amount(amount, f"{currency} ")
    return replace(b, group=f"{shown} for {travelers} travelers")


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

    A part that is 0 is left out, except an "(included)" part (#1527). The text is plain: the template escapes it (P5).
    """
    if b.no_rate:
        return f"no rate for {b.no_rate}"
    shown = b.group or b.original  # the group price (#767) or the price in its own currency (#385)
    price_label = f"{shown} ({_amount(b.price)}) price" if shown else None
    labels = (("price", b.price), ("time", b.time_cost), ("transfers", b.transfer_cost)) + b.extras
    parts = [price_label if label == "price" and price_label else f"{_amount(value)} {label}"
             for label, value in labels if value != 0 or label.endswith("(included)")]  # #1527
    if not parts:
        return _amount(b.total)
    return f"{' + '.join(parts)} = {_amount(b.total)}"
