"""The grid of a round trip (#1107): the sum of the best totals per outbound day and return day."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.days import Day, day_summary, return_grid


def _day(day: str, total: str | None) -> Day:
    if total is None:
        return Day(day, None, None, 0)
    row = (SimpleNamespace(hidden=False), None, SimpleNamespace(total=Decimal(total)))
    return Day(day, row, row, 1)


def test_nine_cells_are_sums_of_the_two_best_totals():
    out = [_day("2026-05-01", "10"), _day("2026-05-02", "20"), _day("2026-05-03", "30")]
    back = [_day("2026-05-10", "1"), _day("2026-05-11", "2.5"), _day("2026-05-12", "3")]
    grid = return_grid(out, back)
    assert len(grid.cells) == 9
    assert grid.outbound == ["2026-05-01", "2026-05-02", "2026-05-03"]
    assert grid.back == ["2026-05-10", "2026-05-11", "2026-05-12"]
    totals = {(c.outbound, c.back): c.total for c in grid.cells}
    assert totals[("2026-05-02", "2026-05-11")] == Decimal("22.5")
    assert totals[("2026-05-03", "2026-05-12")] == Decimal("33")
    assert all(isinstance(c.total, Decimal) for c in grid.cells)


def test_day_without_row_gives_none_cell():
    out = [_day("2026-05-01", "10"), _day("2026-05-02", None)]
    back = [_day("2026-05-10", "1")]
    grid = return_grid(out, back)
    totals = {(c.outbound, c.back): c.total for c in grid.cells}
    assert totals[("2026-05-02", "2026-05-10")] is None
    assert totals[("2026-05-01", "2026-05-10")] == Decimal("11")


def test_return_day_before_outbound_day_gives_none_cell():
    out = [_day("2026-05-05", "10")]
    back = [_day("2026-05-04", "1"), _day("2026-05-05", "2"), _day("2026-05-06", "3")]
    grid = return_grid(out, back)
    totals = {(c.outbound, c.back): c.total for c in grid.cells}
    assert totals[("2026-05-05", "2026-05-04")] is None
    assert totals[("2026-05-05", "2026-05-05")] == Decimal("12")
    assert totals[("2026-05-05", "2026-05-06")] == Decimal("13")


def test_best_cell_is_lowest_finite_sum():
    out = [_day("2026-05-01", "10"), _day("2026-05-02", "5")]
    back = [_day("2026-05-10", "4"), _day("2026-05-11", "1")]
    grid = return_grid(out, back)
    assert grid.best is not None
    assert (grid.best.outbound, grid.best.back, grid.best.total) == ("2026-05-02", "2026-05-11", Decimal("6"))


def test_infinite_sum_is_not_best():
    out = [_day("2026-05-01", "Infinity")]
    back = [_day("2026-05-10", "1"), _day("2026-05-11", "7")]
    grid = return_grid(out, back)
    assert all(c.total == Decimal("Infinity") for c in grid.cells)
    assert grid.best is None


def test_no_best_cell_when_all_cells_are_none():
    out = [_day("2026-05-01", None)]
    back = [_day("2026-05-10", "1")]
    grid = return_grid(out, back)
    assert grid.cells[0].total is None
    assert grid.best is None


def test_range_of_20_days_gives_14_days():
    rows = []
    out = day_summary(rows, date(2026, 5, 1), date(2026, 5, 20), lambda it: None)
    back = day_summary(rows, date(2026, 6, 1), date(2026, 6, 20), lambda it: None)
    assert len(out) == 20 and len(back) == 20
    grid = return_grid(out, back)
    assert len(grid.outbound) == 14
    assert len(grid.back) == 14
    assert len(grid.cells) == 14 * 14
