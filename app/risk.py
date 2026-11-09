"""The risk extras of an offer (epic #172, docs/SPEC.md section 7.2 "Risky transfers") and the mode markup (#174)."""

from datetime import timedelta
from decimal import Decimal

from app.ranking import Weights

MODE_FIELDS = {"train": "train_markup", "bus": "bus_markup", "flight": "flight_markup", "ferry": "ferry_markup"}


def mode_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """One part ("<mode> markup", amount) for each mode of the itinerary that has a markup. A negative amount is a
    discount. A markup of 0 adds no part. The modes come from `mode_summary` ("train+bus")."""
    parts = []
    for mode in dict.fromkeys(m for m in (itinerary.mode_summary or "").split("+") if m):
        field = MODE_FIELDS.get(mode)
        amount = Decimal(getattr(weights, field)) if field else Decimal("0")
        if amount != 0:
            parts.append((f"{mode} markup", amount))
    return tuple(parts)


def transfer_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add one part "short transfer" for the short transfers: the penalty times their count.

    A transfer is the time from the arrival of one leg to the departure of the next one (both UTC, so no offset is
    needed). A penalty of 0 adds no part.
    """
    penalty = Decimal(weights.short_transfer_penalty)
    if penalty == 0 or len(itinerary.legs) < 2:
        return ()
    minimum = timedelta(minutes=weights.short_transfer_min)
    # A change of station uses its own minimum (#1501); None keeps the short-transfer minimum for it too.
    changes = set(station_changes(itinerary)) if weights.station_change_min is not None else set()
    change_minimum = timedelta(minutes=int(weights.station_change_min)) if changes else minimum
    short = sum(1 for i, (before, after) in enumerate(zip(itinerary.legs, itinerary.legs[1:]))
                if after.depart_at - before.arrive_at < (change_minimum if i in changes else minimum))
    if short == 0:
        return ()
    return (("short transfer", penalty * short),)


def station_change_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add one part "change of station": the penalty times the count of changes of station (#1501).

    A penalty of 0 adds no part.
    """
    penalty = Decimal(weights.station_change_penalty)
    if penalty == 0 or len(itinerary.legs) < 2:
        return ()
    count = len(station_changes(itinerary))
    if count == 0:
        return ()
    return (("change of station", penalty * count),)


def station_changes(itinerary) -> list[int]:
    """The indexes i of the transfers where legs[i] arrives at another station than legs[i + 1] departs from (#1500).

    The codes are compared when both are set, else the names: case and spaces do not count. No score part is added.
    """
    return [i for i, (before, after) in enumerate(zip(itinerary.legs, itinerary.legs[1:]))
            if other_station(before, after)]


def other_station(before, after) -> bool:
    """True when the leg `before` arrives at another station than the leg `after` departs from (#1500, #1502).

    One rule for the transfers of an itinerary and for the pairs of the split trips.
    """
    return not _same_station(before, after)


def _same_station(before, after) -> bool:
    if before.to_code and after.from_code:
        return before.to_code == after.from_code
    return _name_key(before.to_name) == _name_key(after.from_name)


def _name_key(name: str) -> str:
    return " ".join(name.split()).casefold()


def stale_extras(it, weights: Weights, stale_before) -> tuple[tuple[str, Decimal], ...]:
    """Add one part "stale" when the newest capture of the itinerary is older than `stale_before` (#276).

    A penalty of 0 adds no part.
    """
    penalty = Decimal(weights.stale_penalty)
    if penalty == 0 or not it.fares:
        return ()
    if max(f.latest_captured_at for f in it.fares) < stale_before:
        return (("stale", penalty),)
    return ()


def self_transfer_extras(fare, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add the penalty for each self-transfer of the fare (#176): one part with the sum. A penalty of 0 adds no part.

    The count is on the fare, not on the itinerary: one source can sell the journey as one ticket, another as two.
    """
    count = fare.self_transfers or 0
    penalty = Decimal(weights.self_transfer_penalty)
    if penalty == 0 or count == 0:
        return ()
    return (("self-transfer", penalty * count),)
