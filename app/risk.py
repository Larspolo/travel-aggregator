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


HOUR_FIELDS = {"train": "train_hour_markup", "bus": "bus_hour_markup", "flight": "flight_hour_markup",
               "ferry": "ferry_hour_markup"}  # (#1567)


def mode_hour_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """One part ("<mode> hours", amount) for each mode with an hour value (#1567): the minutes of its legs times
    (value − hour_markup) / 60. A value of None or a difference of 0 adds no part; another mode adds 0."""
    parts = []
    for mode, field in HOUR_FIELDS.items():
        value = getattr(weights, field)
        if value is None:
            continue
        diff = Decimal(value) - Decimal(weights.hour_markup)
        if diff == 0:
            continue
        seconds = sum(int((leg.arrive_at - leg.depart_at).total_seconds()) for leg in itinerary.legs
                      if leg.mode == mode)
        if seconds:
            parts.append((f"{mode} hours", Decimal(seconds) / 60 * diff / 60))
    return tuple(parts)


def carrier_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """One part ("carrier <name>", amount) for each carrier slot whose name a leg of the itinerary has (#1530). The name
    matches without case and outer spaces. A slot with an empty name or a markup of 0 adds no part. A negative amount
    is a discount. Each slot adds at most one part per itinerary."""
    carriers = {(leg.carrier or "").strip().casefold() for leg in itinerary.legs}
    parts = []
    for n in (1, 2, 3):
        name = getattr(weights, f"carrier{n}_name").strip()
        amount = Decimal(getattr(weights, f"carrier{n}_markup"))
        if name and amount != 0 and name.casefold() in carriers:
            parts.append((f"carrier {name}", amount))
    return tuple(parts)


def transfer_place_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """One part ("transfer at <name>", amount) for each transfer at a marked place (#1850). The name is a part of the
    arrival station or the departure station of the transfer; it matches without case and inner or outer spaces. A slot
    with an empty name or a markup of 0 adds no part. A negative amount is a discount. Two transfers at one place add
    the amount two times."""
    parts = []
    for n in (1, 2, 3):
        name = _name_key(getattr(weights, f"transfer_place{n}_name"))
        amount = Decimal(getattr(weights, f"transfer_place{n}_markup"))
        if not name or amount == 0:
            continue
        for before, after in zip(itinerary.legs, itinerary.legs[1:]):
            if name in _name_key(before.to_name or "") or name in _name_key(after.from_name or ""):
                parts.append((f"transfer at {getattr(weights, f'transfer_place{n}_name').strip()}", amount))
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
    def needed(i, before, after):
        return transfer_minimum(before, after, weights, change_minimum if i in changes else None)

    short = sum(1 for i, (before, after) in enumerate(zip(itinerary.legs, itinerary.legs[1:]))
                if after.depart_at - before.arrive_at < needed(i, before, after))
    if short == 0:
        return ()
    return (("short transfer", penalty * short),)


def transfer_minimum(before, after, weights: Weights, change_minimum=None) -> timedelta:
    """The minimum time of the transfer from the leg `before` to the leg `after`: the minimum of a matched transfer
    place (#2073; with two matches the larger one), else `short_transfer_min`. `change_minimum` (a change of station)
    replaces `short_transfer_min` and wins when it is larger (#2075 uses it for split pairs too)."""
    base = change_minimum if change_minimum is not None else timedelta(minutes=weights.short_transfer_min)
    here = []
    for n in (1, 2, 3):
        name = _name_key(getattr(weights, f"transfer_place{n}_name"))
        m = getattr(weights, f"transfer_place{n}_min")
        if name and m is not None and (name in _name_key(before.to_name or "")
                                       or name in _name_key(after.from_name or "")):
            here.append(timedelta(minutes=int(m)))
    if not here:
        return base
    return max([*here, change_minimum]) if change_minimum is not None else max(here)


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


def reservation_extras(fare, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add the fee for each leg of the fare with a mandatory reservation that its price does not include (#1623): one
    part with the sum. A fee of 0 or no such leg adds no part. The count is on the fare (#1620), as `self_transfers`."""
    count = getattr(fare, "reservation_legs", 0) or 0
    fee = Decimal(weights.reservation_fee)
    if fee == 0 or count == 0:
        return ()
    return (("reservation", fee * count),)
