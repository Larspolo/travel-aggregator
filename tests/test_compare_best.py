"""The compare page marks the best cell of each line: the lowest price, duration, transfers and effective cost (#294)."""

import re

from sqlalchemy import select

from app.models import Itinerary
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _ids(sessions, trip_id):
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
        return {(i.duration_min, i.transfers, i.legs[0].service_no): i.id for i in its}


def _best_rows(page):
    """The row label of each line and the number of its cells with the class best."""
    rows = re.findall(r'<tr><th scope="row">([^<]+)</th>(.*?)</tr>', page)
    return {label: len(re.findall(r'class="[^"]*\bbest\b', cells)) for label, cells in rows}


def _best_cells(page, label):
    row = re.search(rf'<tr><th scope="row">{label}</th>(.*?)</tr>', page).group(1)
    return [m.group(1) for m in re.finditer(r'<td([^>]*)>', row) if "best" in m.group(1)]


def test_the_lowest_price_and_the_shortest_duration_are_marked(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    ids = _ids(sessions, trip_id)
    page = client.get(f"/trips/{trip_id}/compare", params={"it": [ids[(472, 1, "ICE 105")], ids[(240, 0, "ICE 9")]]}).text
    # the first column is the 89.90 offer (472 min), the second the direct 150.00 (240 min)
    assert len(_best_cells(page, "Price")) == 1 and "€89.90" in page.split("Price")[1][:200]
    assert len(_best_cells(page, "Duration")) == 1


def test_each_of_the_four_lines_has_one_best_cell(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    ids = _ids(sessions, trip_id)
    page = client.get(f"/trips/{trip_id}/compare", params={"it": [ids[(472, 1, "ICE 105")], ids[(240, 0, "ICE 9")]]}).text
    counts = _best_rows(page)
    assert counts["Price"] == 1 and counts["Duration"] == 1 and counts["Transfers"] == 1
    assert counts["Effective cost"] == 1


def test_a_tie_marks_every_cell_with_the_lowest_value(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90", "ICE 105"), offer("89.90", "ICE 107")])
    ids = _ids(sessions, trip_id)
    keys = [k for k in ids if k[2] in ("ICE 105", "ICE 107")]
    assert len(keys) == 2
    page = client.get(f"/trips/{trip_id}/compare", params={"it": [ids[k] for k in keys]}).text
    assert len(_best_cells(page, "Price")) == 2 and len(_best_cells(page, "Duration")) == 2
    assert len(_best_cells(page, "Transfers")) == 2
