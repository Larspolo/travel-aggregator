"""The trip page counts the offers that each filter hides (#1452)."""

import re

from app.filtered import hidden_counts
from tests.test_trip_filters_whole import PASS, itinerary
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)

KINDS = ["mode bus", "source db", "max transfers 0", "max duration 120 min", "depart after 07:00", "arrive by 14:00",
         "excluded mode flight", "excluded carrier FlixBus", "hide stale", "day 2026-12-20"]


def test_each_filter_counts_the_rows_that_it_alone_hides():
    rows = [{k} for k in KINDS] + [set(), {"mode bus", "max transfers 0"}]  # one row of each kind, one shown, one by 2
    s = hidden_counts(rows, KINDS)
    assert (s.total, s.shown_of) == (11, 12)  # the row of two filters counts once in the total
    assert s.counts == [(k, 2 if k in ("mode bus", "max transfers 0") else 1) for k in KINDS]


def test_a_filter_that_hides_no_row_is_not_counted():
    s = hidden_counts([set(), {"hide stale"}], KINDS)
    assert (s.total, s.shown_of, s.counts) == (1, 2, [("hide stale", 1)])


TWO = [("2026-12-20T09:00:00+01:00", "2026-12-20T10:00:00+01:00"),
       ("2026-12-20T11:00:00+01:00", "2026-12-20T13:00:00+01:00")]


def test_the_page_shows_the_line_only_when_a_filter_hides_rows(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [itinerary("PASS 1", "90.00", PASS), itinerary("TWO 1", "80.00", TWO),
                                   itinerary("TWO 2", "70.00", TWO)])
    page = re.sub(r"</?a[^>]*>", "", client.get(f"/trips/{trip_id}?max_transfers=0").text)  # the links of #1453
    assert "Filters hide 2 of 3 offers: max transfers 0 hides 2" in page
    assert "Filters hide" not in client.get(f"/trips/{trip_id}").text
    part = client.get(f"/trips/{trip_id}?max_transfers=0", headers={"HX-Request": "true"}).text
    part = re.sub(r"</?a[^>]*>", "", part)
    assert 'id="trip-filtered" class="filtered muted" hx-swap-oob="true"' in part
    assert "max transfers 0 hides 2" in part


def test_each_excluded_value_is_its_own_filter(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [itinerary("PASS 1", "90.00", PASS),
                                   itinerary("BUS 1", "80.00", PASS, mode="bus", carrier="FlixBus")])
    page = re.sub(r"</?a[^>]*>", "", client.get(f"/trips/{trip_id}?exclude_mode=bus&exclude_carrier=FlixBus").text)
    assert "Filters hide 1 of 2 offers: excluded mode bus hides 1 · excluded carrier FlixBus hides 1" in page
