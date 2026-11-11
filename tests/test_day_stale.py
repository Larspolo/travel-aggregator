"""The stale sources per departure day (#2113): `day_stale_sources` in `app/days.py`."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.days import day_stale_sources

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
STALE_BEFORE = NOW - timedelta(hours=24)


def _fare(source, hours_ago):
    return SimpleNamespace(source=source, latest_captured_at=NOW - timedelta(hours=hours_ago))


def _it(day, fares, hidden=False):
    return SimpleNamespace(day=day, fares=fares, hidden=hidden)


def _day_of(it):
    return it.day


def test_old_capture_is_stale_recent_is_not():
    itineraries = [_it("2026-05-03", [_fare("bahn.de", 30)])]
    assert day_stale_sources(itineraries, _day_of, STALE_BEFORE) == {"2026-05-03": ["bahn.de"]}

    itineraries = [_it("2026-05-03", [_fare("bahn.de", 2)])]
    assert day_stale_sources(itineraries, _day_of, STALE_BEFORE) == {}


def test_newest_capture_of_the_day_decides():
    itineraries = [
        _it("2026-05-03", [_fare("bahn.de", 30)]),
        _it("2026-05-03", [_fare("bahn.de", 2)]),
    ]
    assert day_stale_sources(itineraries, _day_of, STALE_BEFORE) == {}


def test_hidden_and_undated_add_nothing():
    itineraries = [
        _it("2026-05-03", [_fare("flixbus", 30)], hidden=True),
        _it(None, [_fare("ryanair", 30)]),
    ]
    assert day_stale_sources(itineraries, _day_of, STALE_BEFORE) == {}


def test_stale_sources_per_day_sorted_and_unique():
    itineraries = [
        _it("2026-05-03", [_fare("trainline", 30), _fare("bahn.de", 40)]),
        _it("2026-05-03", [_fare("bahn.de", 50), _fare("sncf", 1)]),
        _it("2026-05-04", [_fare("bahn.de", 30)]),
    ]
    assert day_stale_sources(itineraries, _day_of, STALE_BEFORE) == {
        "2026-05-03": ["bahn.de", "trainline"],
        "2026-05-04": ["bahn.de"],
    }


def test_no_itineraries_gives_empty_dict():
    assert day_stale_sources([], _day_of, STALE_BEFORE) == {}
