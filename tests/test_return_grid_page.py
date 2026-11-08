"""The grid of a round trip on both trip pages (#1108)."""

import re
from datetime import timedelta

import pytest

from app.models import Itinerary, Leg, Trip
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _shift(sessions, trip_id, service_no, days):
    with sessions() as s:
        it = next(i for i in s.query(Itinerary).filter_by(trip_id=trip_id) if i.legs[0].service_no == service_no)
        for leg in s.query(Leg).filter_by(itinerary_id=it.id):
            leg.depart_at += timedelta(days=days)
            leg.arrive_at += timedelta(days=days)
        it.depart_at += timedelta(days=days)
        it.arrive_at += timedelta(days=days)
        s.commit()


def _day(sessions, trip_id, service_no):
    from app.web.pages import depart_day
    with sessions() as s:
        it = next(i for i in s.query(Itinerary).filter_by(trip_id=trip_id) if i.legs[0].service_no == service_no)
        return depart_day(it)


@pytest.fixture
def round_trip(trip, sessions):  # noqa: F811
    client, auth, out_id = trip
    with sessions() as s:
        back = Trip(title="Zürich – Amsterdam", origin_text="Zürich", destination_text="Amsterdam", return_of_id=out_id)
        s.add(back)
        s.commit()
        back_id = back.id
    ingest(client, auth, out_id, [offer("50.00", "ICE 1"), offer("60.00", "ICE 2")])
    _shift(sessions, out_id, "ICE 2", 1)
    ingest(client, auth, back_id, [offer("80.00", "ICE 9")])
    _shift(sessions, back_id, "ICE 9", 3)
    d9 = _day(sessions, back_id, "ICE 9")
    from datetime import date
    with sessions() as s:
        t = s.get(Trip, back_id)
        t.date_from = date.fromisoformat(d9)
        t.date_to = t.date_from + timedelta(days=1)
        s.commit()
    return client, out_id, back_id, _day(sessions, out_id, "ICE 1"), _day(sessions, out_id, "ICE 2"), d9


def _grid(html):
    m = re.search(r'<details class="card return-grid".*?</details>', html, re.S)
    return m.group(0) if m else None


def test_both_pages_show_the_grid_with_the_best_cell(round_trip):
    client, out_id, back_id, d1, d2, d9 = round_trip
    for tid in (out_id, back_id):
        grid = _grid(client.get(f"/trips/{tid}").text)
        assert grid is not None
        rows = re.findall(r"<tr><th scope=\"row\">(.*?)</th>", grid)
        assert rows == [f"{d1[8:10]}-{d1[5:7]}", f"{d2[8:10]}-{d2[5:7]}"]  # rows are the outbound days
        assert grid.count("—") == 2  # the return day with no offer
        best = re.search(r'<td class="best">(.*?)</td>', grid, re.S).group(1)
        assert ">€" in best and "(best)" in best
        assert grid.count('class="best"') == 1


def test_a_cell_links_to_the_day_of_the_present_trip(round_trip):
    client, out_id, back_id, d1, d2, d9 = round_trip
    out_grid = _grid(client.get(f"/trips/{out_id}").text)
    assert re.search(rf'href="/trips/{out_id}\?[^"]*day={d2}">€\d+<', out_grid)
    assert re.search(rf'class="best"><a href="/trips/{out_id}\?[^"]*day={d1}">€\d+<', out_grid)
    back_grid = _grid(client.get(f"/trips/{back_id}").text)
    assert re.search(rf'href="/trips/{back_id}\?[^"]*day={d9}">€\d+<span class="sr-only"> \(best\)', back_grid)
    page = client.get(f"/trips/{out_id}?day={d2}").text
    assert "ICE 2" in page.split('id="table"')[1] and "ICE 1" not in page.split('id="table"')[1].split("</table>")[0]


def test_no_grid_with_no_link_or_a_multi_city_journey(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    ingest(client, auth, tid, [offer("50.00")])
    assert _grid(client.get(f"/trips/{tid}").text) is None
    with sessions() as s:
        b = Trip(title="B", origin_text="Zürich", destination_text="Wien", return_of_id=tid)
        s.add(b)
        s.flush()
        s.add(Trip(title="C", origin_text="Wien", destination_text="Amsterdam", return_of_id=b.id))
        s.commit()
    assert _grid(client.get(f"/trips/{tid}").text) is None
