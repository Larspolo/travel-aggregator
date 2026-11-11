"""The routes of the trip on the trip page with a route filter (trip:routes, #2225)."""

import html
import re
from urllib.parse import quote

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

ZERO = "hour_markup=0&transfer_markup=0&airport_before_min=0&airport_after_min=0"


def _direct(price, no):
    o = offer(price, no)
    first, second = o["legs"]
    first.update(to_name=second["to_name"], arrive_at=second["arrive_at"])
    o["legs"] = [first]
    return o


def _example(client, auth, trip_id):
    ingest(client, auth, trip_id, [_direct("120.00", "ICE 1"), _direct("130.00", "ICE 2"),
                                   _direct("150.00", "ICE 3"), offer("104.00", "ICE 4"), offer("110.00", "ICE 5")])


def _section(page):
    return re.search(r'<section class="trip-routes[^"]*" id="trip-routes"[^>]*>(.*?)</section>', page, re.S)


def _lines(page):
    return re.findall(r'<a href="[^"]*"[^>]*>(.*?)</a>', _section(page).group(1))


def test_the_example_shows_the_two_routes(trip):  # noqa: F811
    client, auth, trip_id = trip
    _example(client, auth, trip_id)
    lines = _lines(client.get(f"/trips/{trip_id}?{ZERO}").text)
    assert lines == ["Via Basel SBB: 2 offers, effective €104.00 (best), cheapest €104.00",
                     "Direct: 3 offers, effective €120.00 (+€16.00), cheapest €120.00"]


def _sort_links(page):
    return [html.unescape(h) for h in re.findall(r'class="sort" href="([^"]*)"', page)]


def test_the_direct_filter_shows_only_the_three_direct_rows_and_the_sort_links_keep_it(trip):  # noqa: F811
    client, auth, trip_id = trip
    _example(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}?{ZERO}&route=Direct").text
    shown = set(re.findall(r"DB (ICE \d)", page))
    assert shown == {"ICE 1", "ICE 2", "ICE 3"}
    assert _sort_links(page) and all("route=Direct" in h for h in _sort_links(page))
    assert _lines(page)[-1] == "All routes" and len(_lines(page)) == 3  # the other route still shows


def test_a_route_with_a_place_and_all_routes(trip):  # noqa: F811
    client, auth, trip_id = trip
    _example(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}?{ZERO}&route=" + quote("basel sbb")).text
    assert set(re.findall(r"DB (ICE \d)", page)) == {"ICE 4", "ICE 5"}
    links = [html.unescape(h) for h in re.findall(r'<a href="([^"]*)"', _section(page).group(1))]
    assert "route=basel+sbb" in links[0] and "route=Direct" in links[1] and "route=" not in links[2]
    full = client.get(f"/trips/{trip_id}?{ZERO}&route=").text
    assert set(re.findall(r"DB (ICE \d)", full)) == {f"ICE {n}" for n in range(1, 6)}
    assert "All routes" not in _section(full).group(1)


def test_a_weight_change_updates_the_lines_out_of_band(trip):  # noqa: F811
    client, auth, trip_id = trip
    _example(client, auth, trip_id)
    r = client.get(f"/trips/{trip_id}?{ZERO}", headers={"HX-Request": "true"})
    assert 'id="trip-routes" aria-label="Routes" hx-swap-oob="true"' in r.text
    assert "Via Basel SBB: 2 offers, effective €104.00 (best), cheapest €104.00" in r.text


def test_a_trip_with_one_route_shows_no_section(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("104.00", "ICE 4"), offer("110.00", "ICE 5")])
    page = client.get(f"/trips/{trip_id}").text
    assert re.search(r'id="trip-routes"[^>]*hidden', page) and "offers, effective" not in _section(page).group(1)
