"""The best row of each mode of a trip (trip:best-mode)."""

from decimal import Decimal


def best_per_mode(rows) -> list[tuple[str, tuple, Decimal]]:
    """The best row of each mode. `rows` are the `(itinerary, fare, cost)` tuples of `trip_page()`.

    Returns `(mode, row, difference)` tuples: the difference is `cost.total` minus the best `cost.total` of the trip,
    so the best row has 0. The mode is the one mode of the row, "mixed" for two or more modes, and "other" when the
    row has no mode summary. A row with no rate does not count. Per mode, the lowest effective cost wins; a tie goes
    to the earliest departure. The result is ordered by the effective cost, the best first.
    """
    from app.web.pages import local

    best: dict[str, tuple[tuple, tuple]] = {}
    for row in rows:
        it, _fare, cost = row
        if cost.no_rate:
            continue
        mode = _mode(it)
        key = (cost.total, _departure(it, local))
        if mode not in best or key < best[mode][0]:
            best[mode] = (key, row)
    ordered = sorted(best.values(), key=lambda entry: entry[0])
    if not ordered:
        return []
    lowest = ordered[0][0][0]
    return [(_mode(row[0]), row, key[0] - lowest) for key, row in ordered]


def _mode(it) -> str:
    modes = {m for m in (it.mode_summary or "").split("+") if m}
    if not modes:
        return "other"
    if len(modes) == 1:
        return modes.pop()
    return "mixed"


def _departure(it, local):
    first = it.legs[0]
    return local(first.depart_at, first.depart_offset_min)
