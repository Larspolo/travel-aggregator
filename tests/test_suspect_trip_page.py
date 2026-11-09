"""The trip page marks a fare with an implausible price "check the price" and ranks without it (#1605)."""
from sqlalchemy import select

import copy

from tests.test_ingest_api import BODY
from app.models import Fare, Trip
from app.profile_compare import best_by_profile
from app.ranking import Weights
from app.web.pages import best_for_weights
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def later(client, auth, tid, offers):
    """A second capture, one day after the first."""
    body = copy.deepcopy(BODY)
    body.update(trip_id=tid, offers=offers, captured_at="2026-11-04T19:41:00Z")
    assert client.post("/api/ingest", json=body, headers=auth).status_code == 200


def _row(page, it_id):
    row = page[page.index(f'id="it-{it_id}"'):]
    return row[:row.index("</tr>")]


def _ids(sessions):
    with sessions() as s:
        return {f.fare_name and str(f.latest_price): (f.id, f.itinerary_id) for f in s.scalars(select(Fare))}


def test_suspect_fare_is_marked_and_does_not_rank(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    ingest(client, auth, tid, [offer("39.00", "ICE 1"), offer("45.00", "ICE 2")])
    later(client, auth, tid, [offer("3.50", "ICE 1"), offer("45.00", "ICE 2")])
    ids = _ids(sessions)
    suspect_it, good_it = ids["3.50"][1], ids["45.00"][1]
    page = client.get(f"/trips/{tid}").text
    row = _row(page, suspect_it)
    assert "check the price" in row and "The last price was €39.00" in row
    assert "best value" not in row and "cheapest" not in row
    assert "best value" in _row(page, good_it)
    assert "check the price" not in _row(page, good_it)
    assert page.index(f'id="it-{good_it}"') < page.index(f'id="it-{suspect_it}"')
    with sessions() as s:
        it, fare, _ = best_for_weights(s, s.get(Trip, tid), Weights())
        assert fare.id == ids["45.00"][0]
        assert all(b.fare.id == ids["45.00"][0] for b in best_by_profile(s, s.get(Trip, tid)))


def test_trip_with_only_suspect_fares_shows_its_rows(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    ingest(client, auth, tid, [offer("39.00", "ICE 1")])
    later(client, auth, tid, [offer("3.50", "ICE 1")])
    it_id = _ids(sessions)["3.50"][1]
    row = _row(client.get(f"/trips/{tid}").text, it_id)
    assert "check the price" in row and "€3.50" in row
    assert "best value" not in row and "cheapest" not in row and "fastest" not in row
