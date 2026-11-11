"""The booked journeys per year and per mode (#1363): the count, the paid prices in EUR and the hours of travel."""

from dataclasses import dataclass, field
from datetime import UTC, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.co2 import co2_kg
from app.currency import EUR, to_eur
from app.delay_claim import claim
from app.ranking import Weights

YEAR_CSV_COLUMNS = ["date", "route", "modes", "carriers", "status", "paid", "currency", "paid_eur", "refund",
                    "refund_eur", "claim_paid"]


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


def booked(session) -> list:
    """The booked and the cancelled itineraries; a cancelled booking keeps its paid price less the refund (#1687)."""
    from sqlalchemy import or_, select
    from sqlalchemy.orm import selectinload

    from app.models import Itinerary
    return session.scalars(
        select(Itinerary).where(or_(Itinerary.booked.is_(True), Itinerary.cancelled_at.is_not(None)))
        .options(selectinload(Itinerary.legs), selectinload(Itinerary.trip))).all()


def trip_budget(session, trip, rates: dict[str, Decimal]):
    """The budget line of the trip page and the rest of the year of `trip.date_from` (#2376); (None, None) with no budget."""
    from app.models import TravelBudget
    row = session.get(TravelBudget, trip.date_from.year) if trip.date_from else None
    if row is None:
        return None, None
    year = trip.date_from.year
    summary = next((y for y in year_summary(booked(session), rates) if y.year == year), None)
    paid = summary.paid_eur if summary else None
    rest = budget_rest(paid, row.amount)
    amount = f"€{abs(rest):,.2f}"
    # a paid price with no rate is not in the sum: say so, as the page "Travel per year" does (#2410)
    note = " (prices with no rate are not counted)" if summary and summary.missing else ""
    return (f"{amount} left of the budget of {year}" if rest >= 0 else f"{amount} over the budget of {year}") + note, rest


def budget_rest(paid: Decimal | None, budget: Decimal) -> Decimal:
    """The rest of the budget of a year (#2375): budget less the paid sum, negative when over the budget."""
    return budget - (paid if paid is not None else Decimal(0))


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


def _join(values) -> str:
    """The distinct non-empty values in their order, joined for one cell (as `app/web/export.py`)."""
    return "; ".join(dict.fromkeys(v for v in values if v))


def _first_leg_date(it):
    if not it.legs:
        return it.depart_at.astimezone(UTC).date()
    first = it.legs[0]
    return (first.depart_at + timedelta(minutes=first.depart_offset_min)).date()


def _csv_row(it, rates: dict[str, Decimal]) -> list[object]:
    legs = it.legs
    first_name = legs[0].from_name if legs else ""
    last_name = legs[-1].to_name if legs else ""
    cancelled = it.cancelled_at is not None
    paid = it.booked_price
    currency = it.booked_currency or EUR
    paid_eur = to_eur(paid, currency, rates) if paid is not None else None
    refund = refund_eur = None
    if cancelled and paid is not None:
        refund = it.refund_price or Decimal(0)
        net_eur = to_eur(paid - refund, currency, rates)
        refund_eur = paid_eur - net_eur if paid_eur is not None and net_eur is not None else None
    delay_claim = claim(it) if it.claim_paid_at is not None else None
    return [
        _first_leg_date(it).isoformat(),
        f"{first_name or ''} - {last_name or ''}",
        _join(leg.mode for leg in legs),
        _join(leg.carrier for leg in legs),
        "cancelled" if cancelled else "booked",
        paid,
        currency,
        paid_eur,
        refund,
        refund_eur,
        delay_claim.amount if delay_claim is not None else None,
    ]


def year_rows(itineraries, year: int, rates: dict[str, Decimal]) -> list[list[object]]:
    """One row per booked or cancelled itinerary of `year`, in the order of `depart_at`, with the columns of
    `YEAR_CSV_COLUMNS`. Summing `paid_eur` less `refund_eur` gives the paid total of `year_summary()`."""
    chosen = sorted((it for it in itineraries if _year_of(it) == year), key=lambda it: it.depart_at)
    return [_csv_row(it, rates) for it in chosen]
