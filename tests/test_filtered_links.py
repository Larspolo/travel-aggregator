"""Each filter of the line "Filters hide" links to the trip page without only that filter (#1453)."""

import html
import re
from urllib.parse import parse_qs

from tests.test_arrive_by_filter import _set_arrive_by, _two_offers
from tests.test_trip_filters_whole import PASS, itinerary
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)

TWO = [("2026-12-20T09:00:00+01:00", "2026-12-20T10:00:00+01:00"),
       ("2026-12-20T11:00:00+01:00", "2026-12-20T13:00:00+01:00")]


def _link(page, label):
    line = re.search(r'<p id="trip-filtered".*?</p>', page, re.S).group(0)
    href = re.search(r'<a href="([^"]+)">' + re.escape(label) + "</a>", line).group(1)
    return html.unescape(href)


def test_the_link_of_max_transfers_keeps_the_other_filters_the_sort_and_the_weights(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [itinerary("PASS 1", "90.00", PASS), itinerary("TWO 1", "80.00", TWO)])
    page = client.get(f"/trips/{trip_id}?max_transfers=0&max_duration_min=600&sort=depart&dir=desc"
                      "&hour_markup=7").text
    q = parse_qs(_link(page, "max transfers 0").split("?", 1)[1], keep_blank_values=True)
    assert "max_transfers" not in q
    assert q["max_duration_min"] == ["600"] and q["sort"] == ["depart"] and q["dir"] == ["desc"]
    assert float(q["hour_markup"][0]) == 7


def test_the_link_of_one_excluded_mode_keeps_the_other_mode(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [itinerary("PASS 1", "90.00", PASS),
                                   itinerary("FLY 1", "80.00", PASS, mode="flight", carrier="KLM")])
    page = client.get(f"/trips/{trip_id}?exclude_mode=flight&exclude_mode=bus").text
    q = parse_qs(_link(page, "excluded mode flight").split("?", 1)[1])
    assert q["exclude_mode"] == ["bus"]


def test_the_link_of_arrive_by_has_an_empty_latest_arrive_and_shows_the_later_offers(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _set_arrive_by(sessions, trip_id, "14:00")
    _two_offers(client, auth, trip_id)
    href = _link(client.get(f"/trips/{trip_id}").text, "arrive by 14:00")
    assert "latest_arrive=&" in href + "&"
    assert "LATE 2" in client.get(href).text
