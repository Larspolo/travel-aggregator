"""The line "best at €N or less" in the expanded row of each offer that is not the best (#1965)."""

import copy
import re

from tests.test_compare_tradeoff import timed
from tests.test_ingest_api import BODY
from tests.test_travelers_whole import _ingest, setup  # noqa: F401  (setup is a fixture)
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)


def _lines(page):
    return re.findall(r'<p class="best-at muted">(.*?)</p>', page)


def test_the_ice_row_shows_the_price_at_which_it_is_the_best(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("118.00", 1, "ICE 1"), timed("90.00", 3, "ICE 2")])
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "22"}).text
    assert _lines(page) == ["best at €74 or less"]


def test_no_line_when_the_value_is_0_or_less(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("10.00", 1, "ICE 1"), timed("20.00", 3, "ICE 2")])
    assert _lines(client.get(f"/trips/{trip_id}", params={"hour_markup": "20"}).text) == []


def test_a_row_with_the_same_slope_gets_the_line(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("50.00", 2, "ICE 1"), timed("60.50", 2, "ICE 2")])
    assert _lines(client.get(f"/trips/{trip_id}", params={"hour_markup": "20"}).text) == ["best at €50 or less"]


def test_the_source_filter_uses_the_best_row_of_that_source(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("100.00", 1, "ICE 1"), timed("80.00", 3, "ICE 2")])
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, source="nsinternational.com", offers=[timed("10.00", 3, "ICE 2")])
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "20", "source": "bahn.de"}).text
    assert _lines(page) == ["best at €60 or less"]  # 80 - (140 - 120)


def test_a_hidden_row_does_not_change_the_best_row(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("100.00", 1, "ICE 1"), timed("80.00", 3, "ICE 2")])
    o = timed("1.00", 2, "IC 9")
    second = copy.deepcopy(o["legs"][0])
    o["legs"][0] = dict(o["legs"][0], to_name="Basel SBB", arrive_at="2026-12-20T10:00:00+01:00")
    o["legs"].append(dict(second, from_name="Basel SBB", depart_at="2026-12-20T10:10:00+01:00", service_no="IC 10"))
    ingest(client, auth, trip_id, [o])
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "20", "max_transfers": "0"}).text
    assert _lines(page) == ["best at €60 or less"]


def test_a_fare_with_no_rate_gets_no_line(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("100.00", 1, "ICE 1"), dict(timed("1.00", 2, "IC 9"), price_currency="CHF")])
    assert _lines(client.get(f"/trips/{trip_id}", params={"hour_markup": "20"}).text) == []


def test_a_group_fare_uses_the_price_per_traveler(setup):  # noqa: F811
    client, auth, (two, _) = setup
    _ingest(client, auth, two, "bahn.de", "fahrplan-amsterdam-berlin-2-adults.json")
    page = client.get(f"/trips/{two}", params={"hour_markup": "0", "transfer_markup": "0"}).text
    costs = re.findall(r'for 2 travelers \(€([\d.,]+)\)', page)
    lines = _lines(page)
    assert lines and set(lines) == {f"best at €{min(costs, key=float)} or less"}
