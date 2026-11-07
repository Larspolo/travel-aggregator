"""The best offer per departure day of a trip (#710): `day_summary` and the `days` of the trip page context."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.days import day_summary
from app.web import pages
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _row(day, total, price, hidden=False, name="x"):
    it = SimpleNamespace(hidden=hidden, day=day, name=name)
    cost = SimpleNamespace(total=Decimal(total), price=Decimal(price))
    return (it, None, cost)


def _day_of(it):
    return it.day


def test_a_range_gives_each_day_in_order_and_an_empty_day_has_no_row():
    rows = [_row("2026-12-18", "200", "90"), _row("2026-12-19", "150", "120"),
            _row("2026-12-21", "300", "280"), _row("2026-12-22", "210", "200")]
    days = day_summary(rows, date(2026, 12, 18), date(2026, 12, 22), _day_of)
    assert [d.day for d in days] == ["2026-12-18", "2026-12-19", "2026-12-20", "2026-12-21", "2026-12-22"]
    empty = days[2]
    assert empty.best is None and empty.cheapest is None and empty.count == 0


def test_a_row_outside_the_range_gives_a_day_at_the_end():
    rows = [_row("2026-12-18", "200", "90"), _row("2026-12-23", "99", "99")]
    days = day_summary(rows, date(2026, 12, 18), date(2026, 12, 22), _day_of)
    assert [d.day for d in days][-1] == "2026-12-23"
    assert days[-1].count == 1


def test_best_and_cheapest_can_be_different_rows_of_one_day():
    rows = [_row("2026-12-19", "150", "120", name="a"), _row("2026-12-19", "140", "160", name="b")]
    (day,) = day_summary(rows, date(2026, 12, 19), None, _day_of)
    assert day.best[0].name == "b" and day.cheapest[0].name == "a"
    assert day.count == 2


def test_a_hidden_row_is_in_no_day():
    rows = [_row("2026-12-19", "10", "10", hidden=True), _row("2026-12-19", "150", "120")]
    (day,) = day_summary(rows, date(2026, 12, 19), None, _day_of)
    assert day.count == 1 and day.best[2].total == Decimal("150")


def test_without_a_date_to_only_the_first_day_is_in_the_range():
    days = day_summary([], date(2026, 12, 19), None, _day_of)
    assert [d.day for d in days] == ["2026-12-19"]


def test_a_long_range_gives_at_most_31_days():
    days = day_summary([], date(2026, 12, 1), date(2027, 2, 28), _day_of)
    assert len(days) == 31


def test_a_row_without_a_day_is_skipped():
    rows = [_row(None, "10", "10")]
    assert day_summary(rows, date(2026, 12, 19), None, _day_of)[0].count == 0


@pytest.fixture
def captured(monkeypatch):
    """Record the context of each template response of the trip page."""
    seen = []
    original = pages.templates.TemplateResponse

    def spy(request, name, context, *args, **kwargs):
        seen.append(context)
        return original(request, name, context, *args, **kwargs)

    monkeypatch.setattr(pages.templates, "TemplateResponse", spy)
    return seen


def test_the_trip_page_context_has_the_days_before_the_day_filter(trip, captured):  # noqa: F811
    client, auth, tid = trip
    ingest(client, auth, tid, [offer("89.90"), offer("119.90", "ICE 123")])
    r = client.get(f"/trips/{tid}", params={"day": "2026-01-01"})  # a day with no row: no row is shown
    assert r.status_code == 200
    context = captured[-1]
    assert context["rows"] == []
    assert len(context["days"]) == 1 and context["days"][0].count == 2  # the day shows all offers
