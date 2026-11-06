"""The score profiles (#229): "Save as profile" on the trip page stores the weights, a load gives the same weights,
and the migration 0008 upgrades and downgrades."""

import dataclasses
from datetime import time
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect

from app.models import ScoreProfile
from app.profiles import from_config, to_config
from app.ranking import Weights
from tests.test_trip_booked import _alembic, csrf, trip  # noqa: F401 (fixture)

CHANGED = {"hour_markup": "22.5", "transfer_markup": "7", "airport_before_min": "90", "airport_after_min": "15",
           "baggage_fee": "25.00", "early_limit": "07:15", "late_limit": "22:00", "time_window_penalty": "12",
           "night_start": "22:30", "night_end": "05:45", "night_min": "180", "night_adjust": "-20",
           "night_hour_markup": "4", "short_transfer_min": "12", "short_transfer_penalty": "30",
           "train_markup": "-5", "bus_markup": "3", "flight_markup": "40", "ferry_markup": "2",
           "flex_non_refundable": "8", "flex_partly_refundable": "4", "flex_flexible": "-6",
           "self_transfer_penalty": "15", "stale_hours": "48", "stale_penalty": "9"}


def _expected(name, raw):
    default = getattr(Weights, name, None)
    if isinstance(default, time):
        return time.fromisoformat(raw)
    if isinstance(default, int):
        return int(raw)
    return Decimal(raw)


def _profiles(sessions):
    with sessions() as s:
        return [(p.name, p.config_json) for p in s.query(ScoreProfile).order_by(ScoreProfile.id)]


def test_the_form_covers_each_weight():
    assert set(CHANGED) == {f.name for f in dataclasses.fields(Weights)}


def test_a_save_stores_one_row_and_a_load_gives_the_same_weights(trip, sessions):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}").text
    assert "Save as profile" in page and 'action="/profiles"' in page
    data = {"csrf_token": csrf(client, trip_id), "trip_id": trip_id, "name": "Comfort", **CHANGED}
    r = client.post("/profiles", data=data, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{trip_id}"
    rows = _profiles(sessions)
    assert [n for n, _ in rows] == ["Comfort"]
    loaded = from_config(rows[0][1])
    for f in dataclasses.fields(Weights):
        assert getattr(loaded, f.name) == _expected(f.name, CHANGED[f.name]), f.name


def test_a_second_save_with_the_same_name_replaces_the_config(trip, sessions):  # noqa: F811
    client, trip_id = trip
    token = csrf(client, trip_id)
    client.post("/profiles", data={"csrf_token": token, "trip_id": trip_id, "name": "Comfort", **CHANGED})
    client.post("/profiles", data={"csrf_token": token, "trip_id": trip_id, "name": "Comfort", "hour_markup": "30"})
    rows = _profiles(sessions)
    assert len(rows) == 1
    assert from_config(rows[0][1]) == Weights(hour_markup=Decimal("30"))


def test_a_save_without_the_csrf_token_or_out_of_range_stores_nothing(trip, sessions):  # noqa: F811
    client, trip_id = trip
    token = csrf(client, trip_id)
    assert client.post("/profiles", data={"trip_id": trip_id, "name": "X"}).status_code == 403
    r = client.post("/profiles", data={"csrf_token": token, "trip_id": trip_id, "name": "X", "hour_markup": "101"})
    assert r.status_code == 422
    assert _profiles(sessions) == []


@pytest.mark.parametrize("field", [f.name for f in dataclasses.fields(Weights)])
def test_each_field_survives_to_config_and_from_config(field):
    weights = Weights(**{field: _expected(field, CHANGED[field])})
    assert from_config(to_config(weights)) == weights


def test_none_stays_none_and_an_unknown_and_a_missing_key_load():
    config = to_config(Weights())
    assert config["night_hour_markup"] is None and config["early_limit"] == "06:00" and config["hour_markup"] == "15"
    del config["transfer_markup"]
    config["a_weight_of_the_future"] = "1"
    assert from_config(config) == Weights()


def test_migration_0008_up_and_down(empty_database_url):
    cfg = _alembic(empty_database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(empty_database_url)
    try:
        assert "score_profiles" in inspect(engine).get_table_names()
        command.downgrade(cfg, "0007")  # one step below 0008: the head is 0009 now (#232)
        assert "score_profiles" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "head")
    finally:
        engine.dispose()
