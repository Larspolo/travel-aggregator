"""The trip table sends the ticked rows to the compare page (#293): a form with the weights, a box per row."""

import re
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import select

from app.models import Itinerary
from tests.test_profiles_trip import _default_fast, _set_trip_profile
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

FORM = re.compile(r'<form id="compare"[^>]*action="([^"]+)"[^>]*>(.*?)</form>', re.S)
HIDDEN = re.compile(r'<input type="hidden" name="([^"]+)" value="([^"]*)">')
BOXES = re.compile(r'<input type="checkbox" name="it" value="(\d+)" form="compare" aria-label="Compare">')


def _ids(sessions, trip_id):
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
        return {i.duration_min: i.id for i in its}  # 472: offer, 240: direct


def _form(page):
    """The action and the (name, value) pairs of the compare form, parsed from the page."""
    match = FORM.search(page)
    assert match is not None, "no form with id compare"
    return match.group(1), HIDDEN.findall(match.group(2))


def _submit(client, page, ticked):
    """Submit the compare form the way a browser does: its hidden fields plus the ticked boxes."""
    action, fields = _form(page)
    assert all(str(i) in BOXES.findall(page) for i in ticked)
    params = [*fields, *[("it", i) for i in ticked]]
    return client.get(action, params=params)


def test_each_row_has_a_box_with_its_itinerary_id(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    ids = _ids(sessions, trip_id)
    page = client.get(f"/trips/{trip_id}").text
    assert sorted(BOXES.findall(page)) == sorted(str(i) for i in ids.values())


def test_the_form_targets_the_compare_page_of_the_trip(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    action, _ = _form(client.get(f"/trips/{trip_id}").text)
    assert action == f"/trips/{trip_id}/compare"


def test_a_slider_change_keeps_the_boxes_and_updates_the_form(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    ids = _ids(sessions, trip_id)
    # htmx swaps only the table; the form comes out of band with the new weights
    swapped = client.get(f"/trips/{trip_id}", params={"hour_markup": "30"}, headers={"HX-Request": "true"}).text
    assert 'hx-swap-oob="true"' in swapped and 'name="hour_markup" value="30"' in swapped
    assert sorted(BOXES.findall(swapped)) == sorted(str(i) for i in ids.values())


def test_submit_with_two_ticked_rows_opens_the_compare_page(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    ids = _ids(sessions, trip_id)
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "30"}).text
    response = _submit(client, page, [ids[240], ids[472]])
    assert response.status_code == 200 and "Select 2 to 4" not in response.text
    query = parse_qsl(urlsplit(str(response.url)).query)
    assert urlsplit(str(response.url)).path == f"/trips/{trip_id}/compare"
    assert [int(v) for k, v in query if k == "it"] == [ids[240], ids[472]]
    assert ("hour_markup", "30") in query


def test_submit_keeps_the_trip_profile(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    ids = _ids(sessions, trip_id)
    names = _default_fast(sessions)
    _set_trip_profile(sessions, trip_id, names["Cheap"])
    page = client.get(f"/trips/{trip_id}").text
    response = _submit(client, page, [ids[472], ids[240]])
    query = parse_qsl(urlsplit(str(response.url)).query)
    assert ("profile", str(names["Cheap"])) in query and response.status_code == 200
