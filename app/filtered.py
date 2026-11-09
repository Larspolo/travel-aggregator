"""The count of the offers that each filter of the trip page hides (#1452).

A pure module: the trip page gives the result of each filter test per row, and this module counts them.
"""

from dataclasses import dataclass, field


@dataclass
class HiddenSummary:
    """`total`: the rows that one or more filters hide; `shown_of`: all rows; `counts`: (label, rows) per filter."""

    total: int = 0
    shown_of: int = 0
    counts: list[tuple[str, int]] = field(default_factory=list)


def hidden_counts(rows, filters) -> HiddenSummary:
    """Count the rows that each filter alone hides.

    `rows`: one set per row with the labels of the filters that hide it. `filters`: the labels in the order of the
    filter form. A row that two filters hide counts in each, and once in `total`. A filter that hides no row is not
    in `counts`.
    """
    rows = list(rows)
    counts = [(label, sum(1 for r in rows if label in r)) for label in filters]
    return HiddenSummary(total=sum(1 for r in rows if r), shown_of=len(rows),
                         counts=[(label, n) for label, n in counts if n])
