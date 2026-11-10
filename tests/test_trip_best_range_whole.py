"""The whole hour range of the best offer: rows with no rate and hidden rows do not change it (#1937)."""

import copy
import re

from tests.test_compare_tradeoff import timed
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)

BASE = [timed("100.00", 1, "ICE 1"), timed("80.00", 3, "ICE 2")]


def _best(client, trip_id, **params):
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "20", **params}).text
    return re.findall(r'<p class="best-range muted">(.*?)</p>', page, re.S)


def test_a_row_with_no_rate_does_not_change_the_range(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, BASE)
    before = _best(client, trip_id)
    chf = dict(timed("1.00", 2, "IC 9"), price_currency="CHF")
    ingest(client, auth, trip_id, [chf])
    assert before and _best(client, trip_id) == before


def test_a_row_that_a_filter_hides_does_not_change_the_range(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, BASE)
    before = _best(client, trip_id, max_transfers="0")
    o = timed("1.00", 2, "IC 9")
    second = copy.deepcopy(o["legs"][0])
    o["legs"][0] = dict(o["legs"][0], to_name="Basel SBB", arrive_at="2026-12-20T10:00:00+01:00")
    o["legs"].append(dict(second, from_name="Basel SBB", depart_at="2026-12-20T10:10:00+01:00", service_no="IC 10"))
    ingest(client, auth, trip_id, [o])
    assert before and _best(client, trip_id, max_transfers="0") == before
    assert _best(client, trip_id) != before
