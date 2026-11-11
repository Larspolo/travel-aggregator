"""The minimum transfer time of each transfer place of a profile (#2073)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models import ScoreProfile
from app.profiles import from_config
from app.ranking import Weights
from app.risk import transfer_extras
from tests.test_trip_booked import csrf, trip  # noqa: F401 (fixture)

T0 = datetime(2026, 12, 20, 12, 0, tzinfo=timezone.utc)
BASE = {"short_transfer_penalty": Decimal("10"), "short_transfer_min": 10}


def _leg(from_name, to_name, start):
    return SimpleNamespace(from_name=from_name, to_name=to_name, from_code=None, to_code=None, depart_at=start,
                           arrive_at=start + timedelta(minutes=30))


def _via(place, gap_min=45, next_from=None):
    first = _leg("Amsterdam", place, T0)
    return SimpleNamespace(legs=[first, _leg(next_from or place, "Lyon", first.arrive_at + timedelta(minutes=gap_min))])


def test_a_short_transfer_at_the_slot_place_adds_the_penalty():
    w = Weights(**BASE, transfer_place1_name="Paris CDG", transfer_place1_min=60)
    assert transfer_extras(_via("Paris CDG Airport"), w) == (("short transfer", Decimal("10")),)
    assert transfer_extras(_via("Köln Hbf"), w) == ()


def test_a_blank_minimum_or_no_transfer_at_the_place_ranks_as_before():
    assert transfer_extras(_via("Paris CDG"), Weights(**BASE, transfer_place1_name="Paris CDG")) == ()
    w = Weights(**BASE, transfer_place2_name="Bruxelles", transfer_place2_min=60)
    assert transfer_extras(_via("Köln Hbf"), w) == transfer_extras(_via("Köln Hbf"), Weights(**BASE))


def test_two_matches_use_the_larger_minimum_and_a_station_change_keeps_a_larger_one():
    w = Weights(**BASE, transfer_place1_name="Paris", transfer_place1_min=30,
                transfer_place2_name="Paris Nord", transfer_place2_min=50)
    assert transfer_extras(_via("Paris Nord"), w) == (("short transfer", Decimal("10")),)
    w = Weights(**BASE, station_change_min=60, transfer_place1_name="Paris", transfer_place1_min=30)
    assert transfer_extras(_via("Paris Nord", next_from="Paris Lyon"), w) == (("short transfer", Decimal("10")),)


def test_advanced_shows_and_the_profile_stores_the_minimum(trip, sessions):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}?transfer_place1_name=Paris&transfer_place1_min=60").text
    assert 'name="transfer_place1_min"' in page and 'value="60"' in page
    data = {"csrf_token": csrf(client, trip_id), "trip_id": trip_id, "name": "P",
            "transfer_place1_name": "Paris CDG", "transfer_place1_min": "60"}
    assert client.post("/profiles", data=data, follow_redirects=False).status_code == 303
    with sessions() as s:
        loaded = from_config(s.query(ScoreProfile).one().config_json)
    assert loaded.transfer_place1_min == 60 and loaded.transfer_place2_min is None


@pytest.mark.parametrize("value", ["241", "-1"])
def test_an_out_of_range_minimum_stores_nothing(trip, sessions, value):  # noqa: F811
    client, trip_id = trip
    data = {"csrf_token": csrf(client, trip_id), "trip_id": trip_id, "name": "P", "transfer_place3_min": value}
    assert client.post("/profiles", data=data).status_code == 422
    assert client.get(f"/trips/{trip_id}?transfer_place3_min={value}").status_code == 422
    with sessions() as s:
        assert s.query(ScoreProfile).count() == 0
