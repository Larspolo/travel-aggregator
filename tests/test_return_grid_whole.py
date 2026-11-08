"""The whole grid of a round trip (#1109): each cell of the grid is the sum of the best offers of its two days, with the
weights of the journey box. The return trip has its own profile; a slider of the outbound page moves only the
outbound days."""

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import subqueryload

from app.currency import load_rates
from app.days import day_summary, return_grid
from app.models import AccessTime, Itinerary, ScoreProfile, Trip
from app.profiles import to_config
from app.ranking import Weights
from app.web.pages import depart_day, fare_travelers, resolve_weights, row_cost
from tests.test_return_grid_page import _day, _shift
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

# (service number, price, day index of the trip): two offers per day, the second one of a day is the dearer one
OUT_OFFERS = [("ICE 1", "50.00", 0), ("ICE 2", "80.00", 0), ("ICE 3", "60.00", 1),
              ("ICE 4", "75.00", 1), ("ICE 5", "70.00", 2), ("ICE 6", "95.00", 2)]
BACK_OFFERS = [("ICE 11", "40.00", 0), ("ICE 12", "66.00", 0), ("ICE 13", "45.00", 1),
               ("ICE 14", "58.00", 1), ("ICE 15", "55.00", 2), ("ICE 16", "62.00", 2)]
N_DAYS = 3


@pytest.fixture
def grid_trips(trip, sessions):  # noqa: F811
    client, auth, out_id = trip
    with sessions() as s:
        back = Trip(title="Zürich – Amsterdam", origin_text="Zürich", destination_text="Amsterdam", return_of_id=out_id)
        s.add(back)
        s.flush()
        profile = ScoreProfile(name="Long", config_json=to_config(Weights(hour_markup=Decimal("50"))))
        s.add(profile)
        s.flush()
        back.profile_id = profile.id  # the return trip has another profile than the outbound trip
        s.commit()
        back_id = back.id
    ingest(client, auth, out_id, [offer(price, service) for service, price, _ in OUT_OFFERS])
    ingest(client, auth, back_id, [offer(price, service) for service, price, _ in BACK_OFFERS])
    for service, _, day in OUT_OFFERS:
        _shift(sessions, out_id, service, day)
    for service, _, day in BACK_OFFERS:
        _shift(sessions, back_id, service, day)
    first = date.fromisoformat(_day(sessions, out_id, "ICE 1"))
    with sessions() as s:
        for tid in (out_id, back_id):
            t = s.get(Trip, tid)
            t.date_from, t.date_to = first, first + timedelta(days=N_DAYS - 1)
        s.commit()
    return client, out_id, back_id


def _days(s, trip_obj, w, now):
    """The days of one trip with the weights `w`, as the trip page makes them (`day_summary()` of `round_trip_grid`)."""
    stale_before = now - timedelta(hours=w.stale_hours)
    its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_obj.id, Itinerary.hidden.is_(False))
                    .options(subqueryload(Itinerary.legs), subqueryload(Itinerary.fares))).all()
    rates, counts = load_rates(s), fare_travelers(s, its)
    places = s.scalars(select(AccessTime)).all()
    rows = [(it, *row_cost(it, it.fares, places, w, stale_before, rates, counts)) for it in its if it.fares]
    return day_summary(rows, trip_obj.date_from, trip_obj.date_to, lambda it: depart_day(it) if it.legs else None)


def _expected(sessions, out_id, back_id, out_overrides=None):
    """The grid of the round trip: the outbound days with the URL weights of the outbound page, the return days with
    the profile of the return trip."""
    now = datetime.now(timezone.utc)
    with sessions() as s:
        out, back = s.get(Trip, out_id), s.get(Trip, back_id)
        w_out = resolve_weights(s, out, out_overrides or {}, None)[0]
        w_back = resolve_weights(s, back, {}, None)[0]
        return return_grid(_days(s, out, w_out, now), _days(s, back, w_back, now))


def _label(day):
    return f"{day[8:10]}-{day[5:7]}"


def _expected_cells(g):
    cells = {}
    for c in g.cells:
        cells[(_label(c.outbound), _label(c.back))] = (
            "€" + "%.0f" % c.total if c.total is not None and c.total.is_finite() else "—")
    best = (_label(g.best.outbound), _label(g.best.back)) if g.best else None
    return cells, best


def _page_cells(html):
    """The cells and the best cell of the grid of a trip page, as the page shows them."""
    grid = re.search(r'<details class="card return-grid".*?</details>', html, re.S).group(0)
    cols = re.findall(r'<th scope="col">(\d\d-\d\d)</th>', grid)
    cells, best = {}, None
    for row, body in re.findall(r'<tr><th scope="row">(\d\d-\d\d)</th>(.*?)</tr>', grid, re.S):
        tds = re.findall(r'<td( class="best")?>(.*?)</td>', body, re.S)
        assert len(tds) == len(cols)
        for col, (is_best, cell) in zip(cols, tds):
            m = re.search(r"€\d+", cell)
            cells[(row, col)] = m.group(0) if m else "—"
            if is_best:
                best = (row, col)
    return cells, best


def test_each_cell_is_the_sum_of_its_two_best_days_on_both_pages(grid_trips, sessions):
    client, out_id, back_id = grid_trips
    expected_cells, expected_best = _expected_cells(_expected(sessions, out_id, back_id))
    assert len(expected_cells) == N_DAYS * N_DAYS
    assert expected_best is not None
    for page_id in (out_id, back_id):
        cells, best = _page_cells(client.get(f"/trips/{page_id}").text)
        assert cells == expected_cells
        assert best == expected_best


def test_a_slider_on_the_outbound_page_moves_only_the_outbound_days(grid_trips, sessions):
    client, out_id, back_id = grid_trips
    plain, _ = _page_cells(client.get(f"/trips/{out_id}").text)
    moved_out = {"hour_markup": Decimal("0")}
    cells, best = _page_cells(client.get(f"/trips/{out_id}?hour_markup=0").text)
    expected_cells, expected_best = _expected_cells(_expected(sessions, out_id, back_id, moved_out))
    assert cells == expected_cells
    assert best == expected_best
    assert cells != plain  # the outbound weight changes the sums
    # the return days keep their own profile: the return page still shows the grid with no URL weights
    back_cells, _ = _page_cells(client.get(f"/trips/{back_id}").text)
    assert back_cells == _expected_cells(_expected(sessions, out_id, back_id))[0]
