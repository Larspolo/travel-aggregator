"""The risk extras of an offer (epic #172, docs/SPEC.md section 7.2 "Risky transfers") and the mode markup (#174)."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from app.carriers import carrier_names
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


def transfer_wait_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """One part ("transfer wait", amount) for the time between the legs (#2220): the positive waits (the arrival of a
    leg to the departure of the next one, by `seq`) times (value − hour_markup) / 60 / 60. A value of None or a
    difference of 0 adds no part."""
    value = weights.transfer_wait_hour_markup
    if value is None:
        return ()
    diff = Decimal(value) - Decimal(weights.hour_markup)
    if diff == 0:
        return ()
    legs = sorted(itinerary.legs, key=lambda leg: leg.seq)
    seconds = 0
    for before, after in zip(legs, legs[1:]):
        gap = int((after.depart_at - before.arrive_at).total_seconds())
        if gap > 0:
            seconds += gap
    if not seconds:
        return ()
    return (("transfer wait", Decimal(seconds) * diff / 3600),)


def later_transfer_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """One part ("later transfers", amount) for the transfers after the first one (#2302): (transfers − 1) times
    (value − transfer_markup), to 2 places. A value of None, fewer than 2 transfers or a difference of 0 adds no part."""
    value = weights.later_transfer_markup
    if value is None or itinerary.transfers < 2:
        return ()
    diff = Decimal(value) - Decimal(weights.transfer_markup)
    if diff == 0:
        return ()
    amount = Decimal(itinerary.transfers - 1) * diff
    return (("later transfers", amount.quantize(Decimal("0.01"))),)


def _days_off(itinerary) -> frozenset:
    """The days off of the session of `itinerary` (#2371); an itinerary with no session (a plain object) has none."""
    from sqlalchemy.orm.exc import UnmappedInstanceError
    from sqlalchemy.orm import object_session

    from app.days_off import days_off

    try:
        session = object_session(itinerary)
    except UnmappedInstanceError:
        return frozenset()
    return frozenset() if session is None else days_off(session)


def work_hour_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """One part ("work hours", amount) for the minutes of the legs on a local workday (#2332): the minutes between
    work_hour_start:00 and work_hour_end:00 on Monday to Friday that is not a day off (#2371), times (value − hour_markup) / 60. The local times of a
    leg use its departure offset (#2358). A value of None or a difference of 0 adds no part."""
    value = weights.work_hour_markup
    if value is None:
        return ()
    diff = Decimal(value) - Decimal(weights.hour_markup)
    if diff == 0:
        return ()
    off = _days_off(itinerary)
    minutes = 0
    for leg in itinerary.legs:
        start = (leg.depart_at + timedelta(minutes=leg.depart_offset_min)).replace(tzinfo=None)
        end = (leg.arrive_at + timedelta(minutes=leg.depart_offset_min)).replace(tzinfo=None)
        day = start.date()
        while day <= end.date():
            if day.isoweekday() <= 5 and day not in off:
                w_start = datetime.combine(day, time(weights.work_hour_start))
                w_end = datetime.combine(day, time(weights.work_hour_end))
                overlap = min(end, w_end) - max(start, w_start)
                if overlap > timedelta():
                    minutes += int(overlap.total_seconds() // 60)
            day += timedelta(days=1)
    if not minutes:
        return ()
    amount = (Decimal(minutes) * diff / 60).quantize(Decimal("0.01"))
    return (("work hours", amount),)


def work_seat_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """One part ("work seat", amount) for the minutes of the legs with both Wi-Fi and power sockets (#2566): the
    services of a leg are "wifi,power" (None is not known); the amount is minutes × (value − hour_markup) / 60.
    A value of None or a difference of 0 adds no part."""
    value = weights.work_seat_hour_markup
    if value is None:
        return ()
    diff = Decimal(value) - Decimal(weights.hour_markup)
    if diff == 0:
        return ()
    minutes = 0
    for leg in itinerary.legs:
        names = set((leg.services or "").split(","))
        if {"wifi", "power"} <= names:
            minutes += int((leg.arrive_at - leg.depart_at).total_seconds() // 60)
    if not minutes:
        return ()
    amount = (Decimal(minutes) * diff / 60).quantize(Decimal("0.01"))
    return (("work seat", amount),)


def loyalty_extras(itinerary, per: Decimal | None, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """One part ("loyalty <name>", minus the percent of `per`) for each carrier slot whose name each leg of the
    itinerary has (#2432), by the name match of `carrier_extras()`. A fare with no EUR price (`per` None), an empty
    name or a percent of 0 adds no part."""
    if per is None or not itinerary.legs:
        return ()
    legs = [{c.casefold() for c in carrier_names(leg.carrier)}
            | {part.strip().casefold() for part in (leg.carrier or "").split(", ") if part.strip()}
            for leg in itinerary.legs]
    parts = []
    for n in (1, 2, 3):
        name = getattr(weights, f"carrier{n}_name").strip()
        pct = Decimal(getattr(weights, f"carrier{n}_loyalty_pct"))
        if name and pct > 0 and all(name.casefold() in c for c in legs):
            parts.append((f"loyalty {name}", -per * pct / 100))
    return tuple(parts)


def carrier_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """One part ("carrier <name>", amount) for each carrier slot whose name a leg of the itinerary has (#1530). The name
    matches without case and outer spaces, by the names of `carrier_names()` or a part of the raw name (#2249). A slot with an empty name or a markup of 0 adds no part. A negative amount
    is a discount. Each slot adds at most one part per itinerary."""
    carriers = set()
    for leg in itinerary.legs:
        carriers |= {c.casefold() for c in carrier_names(leg.carrier)}
        carriers |= {part.strip().casefold() for part in (leg.carrier or "").split(", ") if part.strip()}
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


def short_transfers(itinerary, weights: Weights) -> list[tuple[int, str | None, int, int]]:
    """The transfers under their minimum (#2074): (index, place, minutes, minimum) for each one. The place is the name
    of the matched transfer place with the minimum in use, else None. One rule for `transfer_extras()` and the row."""
    if len(itinerary.legs) < 2:
        return []
    minimum = timedelta(minutes=weights.short_transfer_min)
    # A change of station uses its own minimum (#1501); None keeps the short-transfer minimum for it too.
    changes = set(station_changes(itinerary)) if weights.station_change_min is not None else set()
    change_minimum = timedelta(minutes=int(weights.station_change_min)) if changes else minimum
    # The minimum of a matched transfer place (#2073): with two matches the larger one; a change of station keeps
    # its own minimum when it is larger.
    slots = [(getattr(weights, f"transfer_place{n}_name"), getattr(weights, f"transfer_place{n}_min"))
             for n in (1, 2, 3)]
    slots = [(_name_key(name), name.strip(), timedelta(minutes=int(m))) for name, m in slots
             if _name_key(name) and m is not None]
    found = []
    for i, (before, after) in enumerate(zip(itinerary.legs, itinerary.legs[1:])):
        here = [(m, label) for key, label, m in slots
                if key in _name_key(before.to_name or "") or key in _name_key(after.from_name or "")]
        base = change_minimum if i in changes else minimum
        need, place = base, None
        if here:
            top, label = max(here, key=lambda h: h[0])
            if i in changes and change_minimum >= top:
                need = change_minimum
            else:
                need, place = top, label
        gap = after.depart_at - before.arrive_at
        if gap < need:
            found.append((i, place, int(gap.total_seconds() // 60), int(need.total_seconds() // 60)))
    return found


def short_place_marks(itinerary, weights: Weights) -> dict[int, str]:
    """The line of each short transfer at a named place with a minimum (#2074), by transfer index."""
    return {i: f"short transfer at {place}: {minutes} min, minimum {need} min"
            for i, place, minutes, need in short_transfers(itinerary, weights) if place}


def transfer_extras(itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add one part "short transfer" for the short transfers: the penalty times their count.

    A transfer is the time from the arrival of one leg to the departure of the next one (both UTC, so no offset is
    needed). A penalty of 0 adds no part. The rule is in `short_transfers()`.
    """
    penalty = Decimal(weights.short_transfer_penalty)
    if penalty == 0:
        return ()
    short = len(short_transfers(itinerary, weights))
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


def bike_extras(fare, itinerary, weights: Weights) -> tuple[tuple[str, Decimal], ...]:
    """Add the fee per leg of a fare with a bicycle reservation on a trip with a bicycle (#2475): one part with the sum.
    A fee of 0, a trip with no bicycle or a fare with another bicycle state adds no part."""
    fee = Decimal(weights.bike_fee)
    if fee == 0 or getattr(getattr(itinerary, "trip", None), "bike", False) is not True:
        return ()
    if getattr(fare, "bike", None) != "reservation":
        return ()
    return (("bicycle", fee * len(itinerary.legs)),)
