"""The rows of the parts of the compare view (#2086)."""

from decimal import Decimal

from app.compare_parts import PartRow, part_rows
from app.ranking import Breakdown, Weights, effective_cost

W = Weights(hour_markup=Decimal("15"))
D = Decimal


def _rows_by_label(rows):
    return {r.label: r for r in rows}


def test_price_and_time_rows_with_diffs():
    a = effective_cost(D("80"), 360, 0, W)
    b = effective_cost(D("120"), 240, 0, W)
    rows = part_rows([a, b])
    by = _rows_by_label(rows)
    assert by["price"] == PartRow("price", (D("80"), D("120")), (None, D("40")))
    assert by["time"] == PartRow("time", (D("90"), D("60")), (None, D("-30")))
    assert "transfers" not in by
    assert [r.label for r in rows] == ["price", "time"]


def test_extra_only_in_second_column_has_zero_first_cell():
    a = effective_cost(D("80"), 360, 0, W)
    b = effective_cost(D("80"), 360, 0, W, extras=(("short transfer", D("20")),))
    by = _rows_by_label(part_rows([a, b]))
    assert by["short transfer"].cells == (D("0"), D("20"))
    assert by["short transfer"].diffs == (None, D("20"))


def test_cells_sum_to_total_for_each_rated_column():
    a = effective_cost(D("80"), 360, 2, W, extras=(("bag", D("5")),))
    b = effective_cost(D("120"), 240, 1, W, extras=(("short transfer", D("20")),))
    c = effective_cost(D("95.50"), 300, 0, W)
    rows = part_rows([a, b, c])
    for n, cost in enumerate([a, b, c]):
        assert sum(r.cells[n] for r in rows) == cost.total


def test_no_rate_column_has_no_price_cell_and_no_diffs():
    a = effective_cost(D("80"), 360, 0, W)
    no_rate = Breakdown(D("Infinity"), D("0"), D("0"), D("Infinity"), no_rate="CHF")
    b = effective_cost(D("120"), 240, 0, W)
    rows = part_rows([a, no_rate, b])
    by = _rows_by_label(rows)
    assert by["price"].cells == (D("80"), None, D("120"))
    assert by["price"].diffs == (None, None, D("40"))
    assert by["time"].diffs == (None, None, D("-30"))


def test_no_rate_column_is_never_best():
    no_rate = Breakdown(D("Infinity"), D("0"), D("0"), D("Infinity"), no_rate="CHF")
    a = effective_cost(D("200"), 60, 0, W)
    rows = part_rows([no_rate, a])
    by = _rows_by_label(rows)
    assert by["price"].diffs == (None, None)  # the only rated column is the best one
    assert by["price"].cells == (None, D("200"))


def test_all_no_rate_gives_no_best_and_no_diffs():
    x = Breakdown(D("Infinity"), D("0"), D("0"), D("Infinity"), no_rate="CHF")
    y = Breakdown(D("Infinity"), D("0"), D("0"), D("Infinity"), no_rate="USD")
    rows = part_rows([x, y])
    assert all(d is None for r in rows for d in r.diffs)


def test_tie_goes_to_first_column():
    a = effective_cost(D("100"), 60, 0, W)
    b = effective_cost(D("100"), 60, 0, W)
    rows = part_rows([a, b])
    assert _rows_by_label(rows)["price"].diffs == (None, D("0"))


def test_included_label_is_kept_when_all_zero():
    a = effective_cost(D("80"), 360, 0, W, extras=(("seat (included)", D("0")),))
    b = effective_cost(D("120"), 240, 0, W, extras=(("seat (included)", D("0")),))
    by = _rows_by_label(part_rows([a, b]))
    assert by["seat (included)"].cells == (D("0"), D("0"))


def test_all_zero_extra_is_left_out():
    a = effective_cost(D("80"), 360, 0, W, extras=(("fee", D("0")),))
    b = effective_cost(D("120"), 240, 0, W)
    assert "fee" not in _rows_by_label(part_rows([a, b]))


def test_empty_list_gives_no_rows():
    assert part_rows([]) == []
