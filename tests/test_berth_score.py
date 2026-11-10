"""The night value of a berth in the effective cost (#1808): "night in a couchette" and so on, else "night travel"."""

import copy
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights
from app.timeofday import night_extras
from app.profiles import from_config
from tests.test_profiles_store import _profiles
from tests.test_trip_booked import csrf
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

UTC = timezone.utc
NIGHT = SimpleNamespace(legs=[SimpleNamespace(depart_at=datetime(2026, 12, 20, 21, tzinfo=UTC), depart_offset_min=0,
                                              arrive_at=datetime(2026, 12, 21, 7, tzinfo=UTC), arrive_offset_min=0)])
DAY = SimpleNamespace(legs=[SimpleNamespace(depart_at=datetime(2026, 12, 20, 9, tzinfo=UTC), depart_offset_min=0,
                                            arrive_at=datetime(2026, 12, 20, 15, tzinfo=UTC), arrive_offset_min=0)])
W = Weights(night_adjust=Decimal("-20"), night_couchette_adjust=Decimal("-40"), night_seat_adjust=Decimal("0"))


def _fare(berth):
    return SimpleNamespace(berth=berth)


def test_each_berth_uses_its_value_and_no_value_uses_night_travel():
    assert night_extras(NIGHT, W, _fare("couchette")) == (("night in a couchette", Decimal("-40")),)
    assert night_extras(NIGHT, W, _fare("seat")) == ()
    assert night_extras(NIGHT, W, _fare("sleeper")) == (("night travel", Decimal("-20")),)
    assert night_extras(NIGHT, W, _fare(None)) == (("night travel", Decimal("-20")),)


def test_empty_values_keep_the_old_part_and_a_day_train_has_none():
    w = Weights(night_adjust=Decimal("-20"))
    for berth in ("seat", "couchette", "sleeper", None):
        assert night_extras(NIGHT, w, _fare(berth)) == night_extras(NIGHT, w) == (("night travel", Decimal("-20")),)
        assert night_extras(DAY, W, _fare(berth)) == ()


def _night(price, fare, berth):
    o = copy.deepcopy(offer(price, "NJ 40", fare=fare))
    o["legs"] = [dict(o["legs"][0], depart_at="2026-12-20T21:00:00+01:00", arrive_at="2026-12-21T08:00:00+01:00")]
    o["berth"] = berth
    return o


def test_the_trip_page_shows_the_part_of_the_berth(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_night("100.00", "Couchette", "couchette")])
    page = client.get(f"/trips/{trip_id}?night_adjust=-20&night_couchette_adjust=-40&night_seat_adjust=0").text
    assert "€-40 night in a couchette" in page and "night travel" not in page
    page = client.get(f"/trips/{trip_id}?night_adjust=-20&night_couchette_adjust=").text
    assert "€-20 night travel" in page and "night in a couchette" not in page
    assert client.get(f"/trips/{trip_id}?night_couchette_adjust=-1001").status_code == 422


def test_a_saved_profile_keeps_the_values_and_an_empty_field_gives_none(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    data = {"csrf_token": csrf(client, trip_id), "trip_id": trip_id, "name": "Berths",
            "night_couchette_adjust": "-40", "night_seat_adjust": "0", "night_sleeper_adjust": ""}
    assert client.post("/profiles", data=data, follow_redirects=False).status_code == 303
    loaded = from_config(_profiles(sessions)[0][1])
    assert (loaded.night_couchette_adjust, loaded.night_seat_adjust, loaded.night_sleeper_adjust) == (
        Decimal("-40"), Decimal("0"), None)
