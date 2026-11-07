"""The time-of-day penalty for an early departure or a late arrival (#141)."""

import copy
from datetime import datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.timeofday import time_extras
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

UTC = timezone.utc
W = Weights(time_window_penalty=Decimal("20"))


def _it(dep_utc, dep_off, arr_utc, arr_off):
    return SimpleNamespace(legs=[SimpleNamespace(depart_at=dep_utc, depart_offset_min=dep_off,
                                                 arrive_at=arr_utc, arrive_offset_min=arr_off)])


def _at(h, m=0, day=20):
    return datetime(2026, 12, day, h, m, tzinfo=UTC)


def test_early_and_late_parts():
    assert time_extras(_it(_at(5), 0, _at(23, 45), 0), W) == (("early departure", Decimal("20")),
                                                              ("late arrival", Decimal("20")))
    assert time_extras(_it(_at(6), 0, _at(23, 30), 0), W) == ()


def test_local_time_of_the_offset_decides():
    # 05:30 UTC is 06:30 at +01:00: not early. 22:45 UTC is 23:45 at +01:00: late.
    assert time_extras(_it(_at(5, 30), 60, _at(22, 45), 60), W) == (("late arrival", Decimal("20")),)
    # 06:30 UTC is 05:30 at -01:00: early.
    assert time_extras(_it(_at(6, 30), -60, _at(12), -60), W) == (("early departure", Decimal("20")),)


def test_zero_penalty_adds_no_part():
    assert time_extras(_it(_at(3), 0, _at(23, 59), 0), Weights()) == ()


def test_custom_limits():
    w = Weights(early_limit=time(8), late_limit=time(20), time_window_penalty=Decimal("5"))
    assert time_extras(_it(_at(7), 0, _at(21), 0), w) == (("early departure", Decimal("5")),
                                                         ("late arrival", Decimal("5")))


def test_trip_page_shows_the_penalty(trip):  # noqa: F811
    client, auth, trip_id = trip
    o = copy.deepcopy(offer("100.00", "ICE 9"))
    o["legs"] = [dict(o["legs"][0], depart_at="2026-12-20T05:00:00+01:00", arrive_at="2026-12-20T09:00:00+01:00")]
    ingest(client, auth, trip_id, [o])
    page = client.get(f"/trips/{trip_id}").text
    assert 'name="early_limit"' in page and 'name="time_window_penalty"' in page and "early departure" not in page
    page = client.get(f"/trips/{trip_id}?time_window_penalty=25&early_limit=06:00").text
    assert "€25 early departure" in page
    assert client.get(f"/trips/{trip_id}?time_window_penalty=-1").status_code == 422
