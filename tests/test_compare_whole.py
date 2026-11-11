"""The compare view works from the ingest API, through the trip table with changed weights, to the compare page (#295)."""

import re

from sqlalchemy import select

from app.models import Itinerary
from tests.test_compare_select import _form, _submit
from tests.test_profiles_trip import _default_fast, _set_trip_profile
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

COST = re.compile(r'<[a-z]+ class="breakdown">([^<]*)</')


def _id_of(sessions, trip_id, service_no):
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
        return next(i.id for i in its if i.legs[0].service_no == service_no)


def _row_cost(page, service_no):
    """The effective cost of the row of the trip table that shows the service."""
    row = next(part for part in page.split("<tr") if f"Deutsche Bahn {service_no}" in part and 'class="cost' in part)
    return COST.findall(row)[0]


def test_the_compare_page_shows_the_costs_of_the_trip_table_with_the_profile_and_weights(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90", "ICE 105"), direct("150.00"), offer("120.00", "ICE 123")])
    names = _default_fast(sessions)
    _set_trip_profile(sessions, trip_id, names["Cheap"])
    ids = {svc: _id_of(sessions, trip_id, svc) for svc in ("ICE 105", "ICE 9", "ICE 123")}

    # the trip table with changed weights; the form of the page sends the 2 ticked rows
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "30"}).text
    action, _fields = _form(page)
    assert action == f"/trips/{trip_id}/compare"
    response = _submit(client, page, [ids["ICE 105"], ids["ICE 9"]])

    assert response.status_code == 200
    assert "Select 2 to 4" not in response.text
    assert "ICE 123" not in response.text  # the third offer has no column
    compare_costs = COST.findall(response.text)
    assert len(compare_costs) == 2
    # each column carries the effective cost of its row of the trip table, in the order of the URL
    assert compare_costs == [_row_cost(page, "ICE 105"), _row_cost(page, "ICE 9")]
