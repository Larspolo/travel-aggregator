"""GET /trips/{id}/compare (#292): 2 to 4 itineraries side by side, with the same effective cost as the trip page."""

import re

from sqlalchemy import select

from app.auth import require_login
from app.main import app
from app.models import Itinerary, Trip
from tests.test_profiles_trip import _default_fast, _set_trip_profile
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct

MESSAGE = "Select 2 to 4 offers of this trip."


def _ids(sessions, trip_id):
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
        return {i.duration_min: i.id for i in its}  # 472: offer, 240: direct


def _costs(page):
    return re.findall(r'<[a-z]+ class="breakdown">([^<]*)</', page)  # a best cost has the class best too (#294)


def _setup(client, auth, trip_id, sessions):
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    ids = _ids(sessions, trip_id)
    return ids[472], ids[240]


def test_two_columns_in_the_order_of_the_url(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    a, b = _setup(client, auth, trip_id, sessions)
    page = client.get(f"/trips/{trip_id}/compare", params={"it": [b, a]}).text
    assert page.index("EUR 150.00") < page.index("EUR 89.90")
    assert "DB ICE 105, SBB IC 61" in page and "Sun 20 Dec 07:34" in page and len(_costs(page)) == 2
    assert f'href="/trips/{trip_id}?' in page and "Back to the trip" in page


def _same_costs(client, trip_id, a, b, params):
    trip_costs = _costs(client.get(f"/trips/{trip_id}", params={**params, "sort": "price"}).text)  # a (89.90) first
    page = client.get(f"/trips/{trip_id}/compare", params={**params, "it": [a, b]}).text
    assert _costs(page) == trip_costs and len(trip_costs) == 2


def test_the_cost_equals_the_trip_page_with_url_weights(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    a, b = _setup(client, auth, trip_id, sessions)
    _same_costs(client, trip_id, a, b, {"hour_markup": "30"})
    assert "hour_markup=30" in client.get(f"/trips/{trip_id}/compare", params={"hour_markup": "30", "it": [a, b]}).text


def test_the_cost_equals_the_trip_page_with_a_trip_profile(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    a, b = _setup(client, auth, trip_id, sessions)
    names = _default_fast(sessions)
    _set_trip_profile(sessions, trip_id, names["Cheap"])
    _same_costs(client, trip_id, a, b, {})


def test_a_wrong_selection_gives_400(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    a, b = _setup(client, auth, trip_id, sessions)
    with sessions() as s:
        other = Trip(title="Other")
        s.add(other)
        s.commit()
        other_id = other.id
    ingest(client, auth, other_id, [offer("70.00")])
    foreign = next(iter(_ids(sessions, other_id).values()))
    for its in ([a], [a, a], [a, b, a + 100, a + 101, a + 102], [a, foreign]):
        r = client.get(f"/trips/{trip_id}/compare", params={"it": its})
        assert r.status_code == 400 and MESSAGE in r.text, its


def test_the_page_needs_the_login(trip):  # noqa: F811
    client, _, trip_id = trip
    app.dependency_overrides.pop(require_login)
    r = client.get(f"/trips/{trip_id}/compare?it=1&it=2", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
