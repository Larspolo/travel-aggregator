"""The timeline bars of the rows of a trip (#813): `timeline` with plain objects, no database."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.timeline import timeline
from app.web.pages import depart_day


def _leg(dep, arr, dep_off=60, arr_off=60, mode="train", from_name="A"):
    """`dep` and `arr` are local 'YYYY-MM-DD HH:MM' times in their offsets (minutes)."""
    def utc(text, off):
        return datetime.fromisoformat(text).replace(tzinfo=timezone(timedelta(minutes=off))).astimezone(timezone.utc)
    return SimpleNamespace(mode=mode, from_name=from_name, depart_at=utc(dep, dep_off), depart_offset_min=dep_off,
                           arrive_at=utc(arr, arr_off), arrive_offset_min=arr_off)


def _row(id_, *legs):
    return (SimpleNamespace(id=id_, hidden=False, legs=list(legs)), None, None)


def test_a_direct_train_and_a_train_with_a_change_give_one_day_with_their_parts():
    rows = [_row(1, _leg("2026-12-18 08:00", "2026-12-18 12:00")),
            _row(2, _leg("2026-12-18 09:30", "2026-12-18 11:00"),
                 _leg("2026-12-18 11:20", "2026-12-18 14:00", from_name="Köln"))]
    days = timeline(rows, depart_day)
    assert len(days) == 1
    day = days[0]
    assert (day.start_min, day.end_min) == (8 * 60, 14 * 60)
    assert [b.itinerary_id for b in day.bars] == [1, 2]
    assert [p.kind for p in day.bars[0].parts] == ["leg"]
    second = day.bars[1].parts
    assert [p.kind for p in second] == ["leg", "gap", "leg"]
    assert (second[1].from_name, second[1].minutes) == ("Köln", 20)
    assert day.bars[0].parts[0].left == 0 and day.bars[1].parts[-1].left + day.bars[1].parts[-1].width == 100


def test_a_flight_to_another_time_zone_keeps_its_true_length():
    rows = [_row(1, _leg("2026-12-18 22:00", "2026-12-18 23:30", 60, 0, mode="flight"))]
    day = timeline(rows, depart_day)[0]
    bar = day.bars[0]
    assert (bar.depart_text, bar.arrive_text) == ("22:00", "23:30")
    assert day.end_min == 1500 and day.end_min - day.start_min >= 360
    leg = bar.parts[0]
    assert abs(leg.width * (day.end_min - day.start_min) / 100 - 150) < 0.1


def test_a_later_arrival_day_has_plus_one():
    rows = [_row(1, _leg("2026-12-18 22:00", "2026-12-19 06:00"))]
    assert timeline(rows, depart_day)[0].bars[0].arrive_text == "06:00 +1"


def test_two_departure_days_give_two_days_in_date_order():
    rows = [_row(1, _leg("2026-12-19 08:00", "2026-12-19 12:00")), _row(2, _leg("2026-12-18 08:00", "2026-12-18 12:00"))]
    assert [d.day for d in timeline(rows, depart_day)] == ["2026-12-18", "2026-12-19"]


def test_an_itinerary_with_no_legs_is_skipped():
    assert timeline([_row(1)], depart_day) == []
