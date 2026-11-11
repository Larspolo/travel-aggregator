"""The hour range of the best offer in its expanded row on the trip page (#1936)."""

import copy
import re

from tests.test_compare_tradeoff import timed
from tests.test_ingest_api import BODY
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)


def _best(page):
    return re.findall(r'<p class="best-range muted">(.*?)</p>', page, re.S)


def test_the_fast_best_row_shows_its_lower_limit_with_a_link(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("100.00", 1, "ICE 1"), timed("80.00", 3, "ICE 2")])
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "20"}).text
    (line,) = _best(page)
    assert re.sub(r"<[^>]+>", "", line).startswith("best from €10")
    assert "hour_markup=10" in line
    assert page.count('class="tradeoff') == 1


def test_one_offer_shows_no_range(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("100.00", 1, "ICE 1")])
    assert _best(client.get(f"/trips/{trip_id}", params={"hour_markup": "20"}).text) == []


def test_the_source_filter_uses_only_the_fares_of_that_source(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [timed("100.00", 1, "ICE 1"), timed("80.00", 3, "ICE 2")])
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, source="nsinternational.com", offers=[timed("10.00", 3, "ICE 2")])
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "20", "source": "bahn.de"}).text
    (line,) = _best(page)
    assert "hour_markup=10" in line
