"""Rows of the parts of the effective cost for the compare view (#2086)."""

from dataclasses import dataclass
from decimal import Decimal

from app.ranking import Breakdown

ZERO = Decimal("0")


@dataclass(frozen=True)
class PartRow:
    """One part of the effective cost, with a cell per column and its difference to the best column."""

    label: str
    cells: tuple[Decimal | None, ...]
    diffs: tuple[Decimal | None, ...]


def _best_column(costs: list[Breakdown]) -> int | None:
    """The column with the lowest total among the columns with a rate; a tie goes to the first (as best_n, #894)."""
    rated = [(b.total, n) for n, b in enumerate(costs) if not b.no_rate]
    if not rated:
        return None
    lowest = min(total for total, _ in rated)
    return next(n for total, n in rated if total == lowest)


def _amount_of(b: Breakdown, label: str) -> Decimal:
    """The amount of one part in a column; a label that is not in the column has 0."""
    if label == "price":
        return b.price
    if label == "time":
        return b.time_cost
    if label == "transfers":
        return b.transfer_cost
    return sum((amount for name, amount in b.extras if name == label), ZERO)


def part_rows(costs: list[Breakdown]) -> list[PartRow]:
    """Give the rows of the parts: price, time, transfers, then each extra label in order of first appearance.

    A row with only 0 cells is left out, except an "(included)" label. A no-rate column has no price cell and
    no differences, and it is never the best column.
    """
    labels = ["price", "time", "transfers"]
    for b in costs:
        for name, _ in b.extras:
            if name not in labels:
                labels.append(name)
    best = _best_column(costs)
    rows = []
    for label in labels:
        cells: list[Decimal | None] = []
        for b in costs:
            if b.no_rate and label == "price":
                cells.append(None)
            else:
                cells.append(_amount_of(b, label))
        if all(cell == ZERO for cell in cells) and not label.endswith("(included)"):
            continue
        diffs: list[Decimal | None] = []
        for n, b in enumerate(costs):
            if best is None or n == best or b.no_rate:
                diffs.append(None)
            else:
                diffs.append(cells[n] - cells[best])
        rows.append(PartRow(label, tuple(cells), tuple(diffs)))
    return rows
