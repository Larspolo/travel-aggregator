"""The booked journeys per year and per mode (#1363): the count, the paid prices in EUR and the hours of travel."""

from dataclasses import dataclass, field
from datetime import UTC, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.co2 import co2_kg
from app.currency import EUR, to_eur
from app.ranking import Weights


@dataclass
class ModeSummary:
    mode: str
    journeys: int
    paid_eur: Decimal | None
    hours: int
    co2_kg: Decimal


@dataclass
class YearSummary:
    year: int
    journeys: int
    paid_eur: Decimal | None
    missing: dict[str, int]
    hours: int
    co2_kg: Decimal
    modes: list[ModeSummary]


@dataclass
class _Acc:
    journeys: int = 0
    minutes: int = 0
    paid: Decimal | None = None
    missing: dict[str, int] = field(default_factory=dict)
    co2: Decimal = Decimal(0)


def _hours(minutes: int) -> int:
    return int((Decimal(minutes) / 60).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _kg(kg: Decimal) -> Decimal:
    return kg.quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _leg_minutes(leg) -> int:
    return int((leg.arrive_at - leg.depart_at).total_seconds() // 60)


def _year_of(it) -> int:
    """The local year of the first leg; an itinerary with no legs uses its departure in UTC."""
    if not it.legs:
        return it.depart_at.astimezone(UTC).year
    first = it.legs[0]
    return (first.depart_at + timedelta(minutes=first.depart_offset_min)).year


def _mode_of(it) -> str:
    """The mode with the most leg minutes; a tie goes to the first such leg."""
    if not it.legs:
        return "unknown"
    minutes: dict[str, int] = {}
    for leg in it.legs:
        minutes[leg.mode] = minutes.get(leg.mode, 0) + _leg_minutes(leg)
    best = max(minutes.values())
    return next(leg.mode for leg in it.legs if minutes[leg.mode] == best)


def _add(acc: _Acc, it, rates: dict[str, Decimal], weights: Weights) -> None:
    # A cancelled booking is no journey (#1687): its paid price less the refund stays in the total.
    cancelled = it.cancelled_at is not None
    if not cancelled:
        acc.journeys += 1
        acc.minutes += it.duration_min
        acc.co2 += co2_kg(it, weights)
    if it.booked_price is None:
        return
    currency = it.booked_currency or EUR
    amount = it.booked_price - (it.refund_price or Decimal(0)) if cancelled else it.booked_price
    eur = to_eur(amount, currency, rates)
    if eur is None:
        acc.missing[currency] = acc.missing.get(currency, 0) + 1
    else:
        acc.paid = eur if acc.paid is None else acc.paid + eur


def year_summary(itineraries, rates: dict[str, Decimal], weights: Weights | None = None) -> list[YearSummary]:
    """The booked itineraries per year, newest year first. A paid price with no rate is counted in `missing`.

    The kg of CO₂ per traveler use `weights` (the `Weights` defaults when None), rounded to whole kg at the end.
    """
    weights = weights or Weights()
    years: dict[int, _Acc] = {}
    modes: dict[tuple[int, str], _Acc] = {}
    for it in itineraries:
        year, mode = _year_of(it), _mode_of(it)
        _add(years.setdefault(year, _Acc()), it, rates, weights)
        _add(modes.setdefault((year, mode), _Acc()), it, rates, weights)
    result = []
    for year in sorted(years, reverse=True):
        acc = years[year]
        lines = [ModeSummary(mode, m.journeys, m.paid, _hours(m.minutes), _kg(m.co2))
                 for (y, mode), m in modes.items() if y == year]
        lines.sort(key=lambda s: (-s.journeys, s.mode))
        result.append(YearSummary(year, acc.journeys, acc.paid, acc.missing, _hours(acc.minutes), _kg(acc.co2), lines))
    return result
