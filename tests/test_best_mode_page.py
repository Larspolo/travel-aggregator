"""The best offer of each mode on the trip page (trip:best-mode, #2192)."""

import re

from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


ZERO = "hour_markup=0&transfer_markup=0&airport_before_min=0&airport_after_min=0"


def _of(mode, price, no):
    o = offer(price, no)
    for leg in o["legs"]:
        leg["mode"] = mode
    return o


def _lines(page):
    m = re.search(r'<section class="trip-best-mode[^"]*" id="trip-best-mode"[^>]*>(.*?)</section>', page, re.S)
    return re.findall(r'<a href="#it-\d+">(.*?)</a>', m.group(1))


def _example(client, auth, trip_id):
    ingest(client, auth, trip_id, [_of("flight", "140.00", "KL 1"), _of("train", "152.00", "ICE 1"),
                                   _of("train", "170.00", "ICE 2"), _of("flight", "160.00", "KL 2")])


def test_the_example_shows_the_flight_best_and_the_train_difference(trip):  # noqa: F811
    client, auth, trip_id = trip
    _example(client, auth, trip_id)
    lines = _lines(client.get(f"/trips/{trip_id}?{ZERO}").text)
    assert len(lines) == 2 and not any(line.startswith("Bus") for line in lines)
    assert lines[0] == "Flight: effective €140.00 (best)" and lines[1] == "Train: effective €152.00 (+€12.00)"


def test_a_filter_that_hides_the_flight_and_one_mode(trip):  # noqa: F811
    client, auth, trip_id = trip
    _example(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}?exclude_mode=flight").text
    assert re.search(r'id="trip-best-mode"[^>]*hidden', page) and "effective €" not in page.split("trip-best-mode")[1]


def test_the_htmx_table_updates_the_lines_out_of_band(trip):  # noqa: F811
    client, auth, trip_id = trip
    _example(client, auth, trip_id)
    r = client.get(f"/trips/{trip_id}?{ZERO}", headers={"HX-Request": "true"})
    assert 'id="trip-best-mode" aria-label="Best offer of each mode" hx-swap-oob="true"' in r.text
    assert "Flight: effective €140.00 (best)" in r.text
