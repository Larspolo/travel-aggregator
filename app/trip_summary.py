"""The text summary of the best rows of a trip, for the "Copy summary" button of the trip page (#2161)."""


def trip_summary(rows, n: int = 3) -> str:
    """One line per row of the `n` best rows. `rows` are the `(itinerary, fare, cost)` tuples of `trip_page()`.

    The rows are ordered by the effective cost, then by the departure. A row with no rate does not count. With fewer
    rows, there is one line per row; with no rows, the text is empty.
    """
    from app.web.pages import local

    usable = [row for row in rows if not row[2].no_rate]
    usable.sort(key=lambda row: (row[2].total, _departure(row[0], local)))
    return "\n".join(_line(it, fare, cost) for it, fare, cost in usable[:n])


def _departure(it, local):
    first = it.legs[0]
    return local(first.depart_at, first.depart_offset_min)


def _line(it, fare, cost) -> str:
    """The texts of `trip_rows.html`, joined by " · ": the times, the transfers, the price, the effective cost and
    the source."""
    from app.money import money
    from app.web.pages import day_gap, local

    first, last = it.legs[0], it.legs[-1]
    dep = local(first.depart_at, first.depart_offset_min)
    arr = local(last.arrive_at, last.arrive_offset_min)
    days = day_gap(arr, dep)
    times = f"{dep.strftime('%a %d %b %H:%M')} → {arr.strftime('%H:%M')}"
    if days > 0:
        times += f" +{days} day" + ("" if days == 1 else "s")
    transfers = f"{it.transfers} transfer" + ("" if it.transfers == 1 else "s")
    return " · ".join([
        times,
        transfers,
        money(fare.latest_price, fare.currency),
        f"effective {money(cost.total)}",
        fare.source,
    ])
