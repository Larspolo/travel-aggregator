"""The change of station at a transfer of an itinerary (#1500)."""

import copy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.risk import station_changes
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

UTC = timezone.utc
T0 = datetime(2026, 12, 20, 12, 0, tzinfo=UTC)


def _leg(from_name, to_name, from_code=None, to_code=None, start=T0):
    return SimpleNamespace(from_name=from_name, to_name=to_name, from_code=from_code, to_code=to_code,
                           depart_at=start, arrive_at=start + timedelta(minutes=30))


def _it(*legs):
    return SimpleNamespace(legs=list(legs))


def test_codes_that_differ_give_a_change_of_station():
    it = _it(_leg("Amsterdam", "Paris Nord", to_code="FRPNO"),
             _leg("Paris Gare de Lyon", "Lyon", from_code="FRLYS"))
    assert station_changes(it) == [0]


def test_equal_codes_give_no_change_even_if_the_names_differ():
    it = _it(_leg("Amsterdam", "Paris Nord", to_code="FRPNO"),
             _leg("Paris Nord (hall 3)", "Lyon", from_code="FRPNO"))
    assert station_changes(it) == []


def test_without_codes_names_that_differ_only_in_case_or_spaces_give_no_change():
    it = _it(_leg("Amsterdam", "Basel  SBB"), _leg("basel sbb", "Zürich HB"))
    assert station_changes(it) == []


def test_without_codes_different_names_give_a_change():
    it = _it(_leg("Amsterdam", "Paris Nord"), _leg("Paris Gare de Lyon", "Lyon"))
    assert station_changes(it) == [0]


def test_the_indexes_of_several_transfers_are_given():
    it = _it(_leg("A", "B"), _leg("B", "C"), _leg("D", "E"), _leg("E", "F"))
    assert station_changes(it) == [1]


def test_one_leg_gives_no_change():
    assert station_changes(_it(_leg("Amsterdam", "Paris Nord"))) == []


def test_the_expanded_row_shows_a_change_of_station_and_a_transfer_at_the_same_station(trip):  # noqa: F811
    client, auth, trip_id = trip
    o = copy.deepcopy(offer("89.90"))
    o["legs"][0]["to_name"] = "Paris Nord"
    o["legs"][1]["from_name"] = "Paris Gare de Lyon"
    ingest(client, auth, trip_id, [o])
    page = client.get(f"/trips/{trip_id}").text
    assert "Change of station: Paris Nord → Paris Gare de Lyon" in page

    same = copy.deepcopy(offer("119.90", service_no="ICE 123"))
    ingest(client, auth, trip_id, [same])
    page = client.get(f"/trips/{trip_id}").text
    assert "Transfer at Basel SBB" in page
