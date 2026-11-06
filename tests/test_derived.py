"""Derived values of an itinerary, computed at ingest (ticket #29)."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.derived import Leg, derive

UTC = timezone.utc
AMS = ZoneInfo("Europe/Amsterdam")


def _leg(depart: datetime, arrive: datetime, mode: str = "train") -> Leg:
    return Leg(depart_at=depart, arrive_at=arrive, mode=mode)


def test_two_legs_with_a_12_minute_gap():
    legs = [
        _leg(datetime(2026, 5, 1, 8, 0, tzinfo=UTC), datetime(2026, 5, 1, 9, 0, tzinfo=UTC), "train"),
        _leg(datetime(2026, 5, 1, 9, 12, tzinfo=UTC), datetime(2026, 5, 1, 10, 0, tzinfo=UTC), "bus"),
    ]
    result = derive(legs)
    assert result.transfers == 1
    assert result.min_transfer_min == 12
    assert result.duration_min == 120
    assert result.mode_summary == "train+bus"


def test_duration_across_a_daylight_saving_change_is_the_true_duration():
    # 2026-03-29 02:00 local time in Amsterdam jumps to 03:00 (CET to CEST).
    depart = datetime(2026, 3, 29, 1, 0, tzinfo=AMS)  # 00:00 UTC
    arrive = datetime(2026, 3, 29, 3, 30, tzinfo=AMS)  # 01:30 UTC
    result = derive([_leg(depart, arrive)])
    assert result.duration_min == 90  # the wall clock shows 150 minutes


def test_legs_with_different_offsets_use_utc_instants():
    legs = [
        _leg(datetime(2026, 5, 1, 8, 0, tzinfo=AMS), datetime(2026, 5, 1, 9, 0, tzinfo=AMS)),
        _leg(
            datetime(2026, 5, 1, 7, 30, tzinfo=timezone(timedelta(hours=0))),
            datetime(2026, 5, 1, 8, 30, tzinfo=timezone(timedelta(hours=0))),
            "bus",
        ),
    ]
    result = derive(legs)
    # The second leg departs 07:30 UTC = 09:30 Amsterdam: a gap of 30 minutes.
    assert result.min_transfer_min == 30
    assert result.duration_min == 150


def test_one_leg_has_no_transfer_time():
    result = derive([_leg(datetime(2026, 5, 1, 8, 0, tzinfo=UTC), datetime(2026, 5, 1, 9, 0, tzinfo=UTC))])
    assert result.transfers == 0
    assert result.min_transfer_min is None
    assert result.mode_summary == "train"


def test_smallest_gap_is_reported_for_three_legs():
    legs = [
        _leg(datetime(2026, 5, 1, 8, 0, tzinfo=UTC), datetime(2026, 5, 1, 9, 0, tzinfo=UTC), "train"),
        _leg(datetime(2026, 5, 1, 9, 30, tzinfo=UTC), datetime(2026, 5, 1, 10, 0, tzinfo=UTC), "bus"),
        _leg(datetime(2026, 5, 1, 10, 5, tzinfo=UTC), datetime(2026, 5, 1, 11, 0, tzinfo=UTC), "train"),
    ]
    result = derive(legs)
    assert result.transfers == 2
    assert result.min_transfer_min == 5
    assert result.mode_summary == "train+bus+train"


def test_repeated_modes_are_removed_from_the_summary():
    legs = [
        _leg(datetime(2026, 5, 1, 8, 0, tzinfo=UTC), datetime(2026, 5, 1, 9, 0, tzinfo=UTC), "train"),
        _leg(datetime(2026, 5, 1, 9, 10, tzinfo=UTC), datetime(2026, 5, 1, 10, 0, tzinfo=UTC), "train"),
        _leg(datetime(2026, 5, 1, 10, 10, tzinfo=UTC), datetime(2026, 5, 1, 11, 0, tzinfo=UTC), "bus"),
    ]
    assert derive(legs).mode_summary == "train+bus"


def test_naive_datetime_raises_value_error():
    naive = datetime(2026, 5, 1, 8, 0)
    aware = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        derive([_leg(naive, aware)])
    with pytest.raises(ValueError):
        derive([_leg(aware, naive)])


def test_no_legs_raises_value_error():
    with pytest.raises(ValueError):
        derive([])
