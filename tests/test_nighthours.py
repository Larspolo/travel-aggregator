"""The night hour markup (#143)."""

import copy
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights, effective_cost
from app.timeofday import night_time_extras
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

UTC = timezone.utc


def _it(dep, arr, off=0):
    return SimpleNamespace(legs=[SimpleNamespace(depart_at=dep, depart_offset_min=off,
                                                 arrive_at=arr, arrive_offset_min=off)])


def _at(day, h, m=0):
    return datetime(2026, 12, day, h, m, tzinfo=UTC)


NIGHT = _it(_at(20, 21), _at(21, 8))  # 23:00-06:00 inside: 420 night minutes


def test_same_markup_adds_no_part():
    assert night_time_extras(NIGHT, Weights()) == ()
    assert night_time_extras(NIGHT, Weights(night_hour_markup=Decimal("15"))) == ()


def test_lower_markup_lowers_cost_by_night_minutes():
    w = Weights(night_hour_markup=Decimal("5"))
    extras = night_time_extras(NIGHT, w)
    assert extras == (("night hours", Decimal("-70")),)  # 420 min × (5 − 15) / 60
    base = effective_cost(Decimal("100"), 660, 0, Weights())
    cost = effective_cost(Decimal("100"), 660, 0, w, extras)
    assert base.time_cost == cost.time_cost
    assert cost.total == base.total - Decimal("70")


def test_day_trip_adds_no_part():
    assert night_time_extras(_it(_at(20, 9), _at(20, 12)), Weights(night_hour_markup=Decimal("0"))) == ()


def test_trip_page_shows_night_hours(trip):  # noqa: F811
    client, auth, trip_id = trip
    o = copy.deepcopy(offer("100.00", "NJ 40"))
    o["legs"] = [dict(o["legs"][0], depart_at="2026-12-20T21:00:00+01:00", arrive_at="2026-12-21T08:00:00+01:00")]
    ingest(client, auth, trip_id, [o])
    page = client.get(f"/trips/{trip_id}").text
    assert 'name="night_hour_markup"' in page and "night hours" not in page
    assert "night hours" in client.get(f"/trips/{trip_id}?night_hour_markup=5").text
