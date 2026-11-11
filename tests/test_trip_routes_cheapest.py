"""The cheapest price of each route, and the route filter on a weight change (trip:routes, #2241)."""

import re

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_routes_page import ZERO, _direct, _example, _lines, _section

WEIGHTS_FORM = r'<form class="weights"[^>]*>(.*?)</form>'
DIRECT_LINK = r'<a href="[^"]*"( aria-current="true")?>Direct:'


def _weights_form(page):
    return re.search(WEIGHTS_FORM, page, re.S).group(1)


def test_the_route_line_shows_the_cheapest_price_after_the_effective_cost(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [_direct("120.00", "ICE 1"), offer("104.00", "ICE 4")])
    lines = _lines(client.get(f"/trips/{trip_id}?{ZERO}").text)
    assert lines == ["Via Basel SBB: 1 offer, effective €104.00 (best), cheapest €104.00",
                     "Direct: 1 offer, effective €120.00 (+€16.00), cheapest €120.00"]


def test_a_page_with_a_route_has_a_hidden_route_input_in_the_weights_form(trip):  # noqa: F811
    client, auth, trip_id = trip
    _example(client, auth, trip_id)
    form = _weights_form(client.get(f"/trips/{trip_id}?{ZERO}&route=Direct").text)
    assert '<input type="hidden" name="route" value="Direct">' in form


def test_a_page_with_no_route_has_no_route_input_in_the_weights_form(trip):  # noqa: F811
    client, auth, trip_id = trip
    _example(client, auth, trip_id)
    form = _weights_form(client.get(f"/trips/{trip_id}?{ZERO}").text)
    assert 'name="route"' not in form


def test_a_htmx_weight_change_keeps_the_direct_filter(trip):  # noqa: F811
    client, auth, trip_id = trip
    _example(client, auth, trip_id)
    # the fields of the weights form of a page with route=Direct, with one slider changed
    query = f"{ZERO.replace('hour_markup=0', 'hour_markup=5')}&route=Direct"
    r = client.get(f"/trips/{trip_id}?{query}", headers={"HX-Request": "true"})
    assert set(re.findall(r"DB (ICE \d)", r.text)) == {"ICE 1", "ICE 2", "ICE 3"}
    section = _section(r.text).group(1)
    assert re.search(DIRECT_LINK, section).group(1) == ' aria-current="true"'
