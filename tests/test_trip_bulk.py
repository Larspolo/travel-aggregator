"""POST /trips/{id}/itineraries/bulk (#1897): the Hide and Pin buttons of the compare bar hide or pin all ticked
offers at once. An id of another trip gives 404 and changes nothing; a POST without the CSRF token gives 403;
the Compare button still works."""

import re

import pytest
from fastapi.testclient import TestClient

from app import tokens
from app.auth import require_login
from app.main import app
from app.models import Itinerary, Trip
from tests.test_trip_page import ingest, offer


@pytest.fixture
def trips(sessions):
    """A client with the owner login; a trip with three offers and a second trip with one offer."""
    with sessions() as s:
        token = tokens.create(s, "test")
        t = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        other = Trip(title="Berlin – Wien", origin_text="Berlin", destination_text="Wien")
        s.add_all([t, other])
        s.commit()
        trip_id, other_id = t.id, other.id
    app.dependency_overrides[require_login] = lambda: None
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {token}"}
    ingest(client, auth, trip_id, [offer("119.90", "ICE 123"), offer("89.90", "ICE 105"), offer("99.90", "ICE 107")])
    ingest(client, auth, other_id, [offer("59.90", "ICE 9")])
    yield client, trip_id, other_id
    app.dependency_overrides.pop(require_login, None)


def csrf(client, trip_id):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(f"/trips/{trip_id}").text).group(1)


def ids_of(sessions, trip_id):
    with sessions() as s:
        return [i.id for i in s.query(Itinerary).filter(Itinerary.trip_id == trip_id).order_by(Itinerary.id)]


def flags(sessions, ids):
    with sessions() as s:
        return [(i.hidden, i.pinned) for i in (s.get(Itinerary, x) for x in ids)]


def bulk_url(trip_id, action):
    return f"/trips/{trip_id}/itineraries/bulk?action={action}"


def test_hide_hides_all_three_ticked_offers(trips, sessions):
    client, trip_id, _ = trips
    ids = ids_of(sessions, trip_id)
    token = csrf(client, trip_id)
    r = client.post(bulk_url(trip_id, "hide"), data={"csrf_token": token, "it": ids}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/trips/{trip_id}"
    assert flags(sessions, ids) == [(True, False)] * 3


def test_pin_pins_all_three_ticked_offers(trips, sessions):
    client, trip_id, _ = trips
    ids = ids_of(sessions, trip_id)
    token = csrf(client, trip_id)
    r = client.post(bulk_url(trip_id, "pin"), data={"csrf_token": token, "it": ids}, follow_redirects=False)
    assert r.status_code == 303
    assert flags(sessions, ids) == [(False, True)] * 3


def test_an_id_of_another_trip_gives_404_and_changes_nothing(trips, sessions):
    client, trip_id, other_id = trips
    ids = ids_of(sessions, trip_id)
    foreign = ids_of(sessions, other_id)
    token = csrf(client, trip_id)
    r = client.post(bulk_url(trip_id, "hide"), data={"csrf_token": token, "it": [ids[0], foreign[0]]},
                    follow_redirects=False)
    assert r.status_code == 404
    assert flags(sessions, ids) == [(False, False)] * 3
    assert flags(sessions, foreign) == [(False, False)]


def test_an_unknown_action_gives_400_and_changes_nothing(trips, sessions):
    client, trip_id, _ = trips
    ids = ids_of(sessions, trip_id)
    token = csrf(client, trip_id)
    r = client.post(bulk_url(trip_id, "delete"), data={"csrf_token": token, "it": ids}, follow_redirects=False)
    assert r.status_code == 400
    assert flags(sessions, ids) == [(False, False)] * 3


def test_a_post_without_the_csrf_token_gets_403_and_changes_nothing(trips, sessions):
    client, trip_id, _ = trips
    ids = ids_of(sessions, trip_id)
    csrf(client, trip_id)  # the session has a token now; the form sends none
    r = client.post(bulk_url(trip_id, "hide"), data={"it": ids}, follow_redirects=False)
    assert r.status_code == 403
    assert flags(sessions, ids) == [(False, False)] * 3


def test_the_bar_has_hide_and_pin_buttons_and_compare_still_works(trips, sessions):
    client, trip_id, _ = trips
    html = client.get(f"/trips/{trip_id}").text
    assert f'formaction="/trips/{trip_id}/itineraries/bulk?action=hide"' in html
    assert f'formaction="/trips/{trip_id}/itineraries/bulk?action=pin"' in html
    assert 'type="submit" form="compare">' in html and "Compare</button>" in html
    ids = ids_of(sessions, trip_id)
    r = client.get(f"/trips/{trip_id}/compare", params=[("it", ids[0]), ("it", ids[1])])
    assert r.status_code == 200
    assert flags(sessions, ids) == [(False, False)] * 3
