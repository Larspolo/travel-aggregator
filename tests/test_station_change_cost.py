"""The minimum and the penalty of a change of station, in "Advanced" (#1501)."""

import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.profiles import from_config, to_config
from app.ranking import Weights
from app.risk import station_change_extras, transfer_extras
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

UTC = timezone.utc
T0 = datetime(2026, 12, 20, 12, 0, tzinfo=UTC)
PENALTY = Decimal("12")


def _leg(from_name, to_name, start, minutes=30):
    return SimpleNamespace(from_name=from_name, to_name=to_name, from_code=None, to_code=None, depart_at=start,
                           arrive_at=start + timedelta(minutes=minutes))


def _two_legs(gap_min, change):
    """Two 30-minute legs with a gap of `gap_min`; `change` puts another station at the start of the second leg."""
    first = _leg("Paris Nord", "Paris Nord", T0)
    second_start = first.arrive_at + timedelta(minutes=gap_min)
    second = _leg("Paris Gare de Lyon" if change else "Paris Nord", "Lyon", second_start)
    return SimpleNamespace(legs=[first, second])


def test_a_change_of_station_adds_the_penalty_per_change():
    w = Weights(station_change_penalty=PENALTY)
    assert station_change_extras(_two_legs(15, change=True), w) == (("change of station", PENALTY),)


def test_a_transfer_at_the_same_station_adds_no_part():
    w = Weights(station_change_penalty=PENALTY)
    assert station_change_extras(_two_legs(15, change=False), w) == ()


def test_the_defaults_add_no_part_and_keep_the_short_transfer_rule():
    it = _two_legs(30, change=True)
    assert station_change_extras(it, Weights()) == ()
    assert transfer_extras(it, Weights(short_transfer_min=10, short_transfer_penalty=Decimal("20"))) == ()


def test_a_station_change_uses_its_own_minimum():
    w = Weights(short_transfer_min=10, short_transfer_penalty=Decimal("20"), station_change_min=45)
    assert transfer_extras(_two_legs(30, change=True), w) == (("short transfer", Decimal("20")),)
    assert transfer_extras(_two_legs(30, change=False), w) == ()


def test_the_profile_keeps_the_two_fields_and_an_old_profile_takes_the_defaults():
    w = Weights(station_change_min=45, station_change_penalty=PENALTY)
    loaded = from_config(to_config(w))
    assert loaded.station_change_min == 45 and loaded.station_change_penalty == PENALTY
    old = from_config({"short_transfer_min": 10})
    assert old.station_change_min is None and old.station_change_penalty == Decimal("0")


def test_the_trip_page_shows_the_penalty_of_a_change_of_station(trip):  # noqa: F811
    client, auth, trip_id = trip
    o = copy.deepcopy(offer("89.90"))
    o["legs"][0]["to_name"] = "Paris Nord"
    o["legs"][1]["from_name"] = "Paris Gare de Lyon"
    ingest(client, auth, trip_id, [o])
    assert "change of station" not in client.get(f"/trips/{trip_id}").text
    page = client.get(f"/trips/{trip_id}?station_change_penalty=12").text
    assert "€12 change of station" in page
    assert client.get(f"/trips/{trip_id}?station_change_min=241").status_code == 422
