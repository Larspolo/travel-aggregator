"""The night travel bonus or penalty (#142)."""

import copy
from datetime import datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights, effective_cost
from app.timeofday import night_extras
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

UTC = timezone.utc


def _it(dep, arr, off=0):
    return SimpleNamespace(legs=[SimpleNamespace(depart_at=dep, depart_offset_min=off,
                                                 arrive_at=arr, arrive_offset_min=off)])


def _at(day, h, m=0):
    return datetime(2026, 12, day, h, m, tzinfo=UTC)


def test_overlap_of_240_minutes_adds_the_part():
    w = Weights(night_adjust=Decimal("30"))
    assert night_extras(_it(_at(20, 22), _at(21, 3)), w) == (("night travel", Decimal("30")),)  # 240 min
    assert night_extras(_it(_at(20, 22), _at(21, 2, 59)), w) == ()


def test_negative_value_is_a_bonus():
    w = Weights(night_adjust=Decimal("-80"))
    extras = night_extras(_it(_at(20, 21), _at(21, 8)), w)
    assert extras == (("night travel", Decimal("-80")),)
    assert effective_cost(Decimal("100"), 0, 0, w, extras).total == Decimal("20.00")


def test_zero_adds_no_part_and_offset_decides():
    assert night_extras(_it(_at(20, 21), _at(21, 8)), Weights()) == ()
    w = Weights(night_adjust=Decimal("10"))
    # 19:00-23:00 UTC is 01:00-05:00 at +06:00: 240 night minutes.
    assert night_extras(_it(_at(20, 19), _at(20, 23), 360), w) == (("night travel", Decimal("10")),)
    assert night_extras(_it(_at(20, 19), _at(20, 23)), w) == ()


def test_window_without_midnight_and_early_morning_span():
    w = Weights(night_start=time(1), night_end=time(5), night_min=60, night_adjust=Decimal("5"))
    assert night_extras(_it(_at(20, 4), _at(20, 6)), w) == (("night travel", Decimal("5")),)
    w = Weights(night_adjust=Decimal("5"))
    assert night_extras(_it(_at(21, 1), _at(21, 6)), w) == (("night travel", Decimal("5")),)


def test_trip_page_shows_night_travel(trip):  # noqa: F811
    client, auth, trip_id = trip
    o = copy.deepcopy(offer("100.00", "NJ 40"))
    o["legs"] = [dict(o["legs"][0], depart_at="2026-12-20T21:00:00+01:00", arrive_at="2026-12-21T08:00:00+01:00")]
    ingest(client, auth, trip_id, [o])
    page = client.get(f"/trips/{trip_id}").text
    assert 'name="night_adjust"' in page and 'name="night_start"' in page and "night travel" not in page
    assert "€-50 night travel" in client.get(f"/trips/{trip_id}?night_adjust=-50").text
