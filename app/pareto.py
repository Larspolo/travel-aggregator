"""The offers that no other offer beats on both the price and the minutes (#1856)."""

from decimal import Decimal


def pareto_ids(points: list[tuple[int, Decimal, int]]) -> set[int]:
    """Give the ids of the (id, price, minutes) points that no other point beats: no other point has a price and
    minutes both less or equal, with one of them less. Equal points all stay in the set."""
    result: set[int] = set()
    best = None  # the lowest minutes of the points with a lower price
    group: list[tuple[int, Decimal, int]] = []
    for point in sorted(points, key=lambda p: (p[1], p[2])) + [None]:
        if group and (point is None or point[1] != group[0][1]):
            low = group[0][2]  # the lowest minutes at this price
            if best is None or low < best:
                result |= {p[0] for p in group if p[2] == low}
                best = low
            group = []
        if point is not None:
            group.append(point)
    return result
