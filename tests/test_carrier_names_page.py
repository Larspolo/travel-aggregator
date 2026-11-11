"""The carrier column of the trip page and the compare view show one name per carrier (#2250)."""

import copy
import re

from tests.test_compare_page import _ids
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _two(client, auth, trip_id):
    a = offer("89.90", carrier="DB Fernverkehr AG")
    b = copy.deepcopy(direct("150.00"))
    b["legs"][0].update(carrier="Deutsche Bahn", service_no="ICE 105")
    ingest(client, auth, trip_id, [a, b])


def test_the_carrier_column_shows_the_mapped_name(trip):  # noqa: F811
    client, auth, trip_id = trip
    _two(client, auth, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    cells = re.findall(r'<td class="carrier"><div class="clip" title="([^"]*)"', page)
    assert len(cells) == 2 and all(c.startswith("Deutsche Bahn ICE 105") for c in cells)
    assert "DB Fernverkehr AG ICE 105" not in cells[0] + cells[1]
    assert re.search(r'class="service">[^<]*(<[^>]*>[^<]*)*?DB Fernverkehr AG ICE 105', page)


def test_the_compare_view_shows_the_mapped_name(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _two(client, auth, trip_id)
    ids = _ids(sessions, trip_id)
    page = client.get(f"/trips/{trip_id}/compare", params={"it": [ids[472], ids[240]]}).text
    row = re.search(r'<th scope="row">Carriers</th>(.*?)</tr>', page).group(1)
    cells = re.findall(r"<td>([^<]*)</td>", row)
    assert len(cells) == 2 and all(c.startswith("Deutsche Bahn") for c in cells)
    assert "DB Fernverkehr" not in row
