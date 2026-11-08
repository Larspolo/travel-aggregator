"""Copy trip (#801): a new trip with the places of a trip, for another date."""

from datetime import date

from app.models import Itinerary, Trip
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_page import ingest, offer


def _fill(sessions, trip_id):
    with sessions() as s:
        trip = s.get(Trip, trip_id)
        trip.origin_text, trip.destination_text, trip.travelers = "Köln", "München", 2
        trip.date_from, trip.date_to = date(2026, 12, 1), date(2026, 12, 3)
        trip.notes = "Bahncard 50"
        s.commit()


def _snapshot(sessions, trip_id):
    with sessions() as s:
        t = s.get(Trip, trip_id)
        return (t.title, t.origin_text, t.destination_text, t.date_from, t.date_to, t.travelers, t.notes,
                t.profile_id, t.return_of_id, s.query(Itinerary).filter_by(trip_id=trip_id).count())


def _post_copy(c, trip_id):
    return c.post(f"/trips/{trip_id}/copy", headers={"X-CSRF-Token": _csrf(c, "/settings")},
                  follow_redirects=False)


def _copies_of(sessions, title):
    with sessions() as s:
        return s.query(Trip).filter(Trip.title == title).all()


def test_the_copy_has_the_places_and_no_dates_link_or_offers(setup, sessions):  # noqa: F811
    c, auth, trip_id = setup
    _fill(sessions, trip_id)
    ingest(c, auth, trip_id, [offer("89.90")])
    r = _post_copy(c, trip_id)
    assert r.status_code == 303
    [new] = _copies_of(sessions, "Köln – München (copy)")
    assert r.headers["location"] == f"/trips/{new.id}/edit"
    assert (new.origin_text, new.destination_text, new.travelers, new.notes) == ("Köln", "München", 2, "Bahncard 50")
    assert new.date_from is None and new.date_to is None
    assert new.return_of_id is None
    with sessions() as s:
        assert s.query(Itinerary).filter_by(trip_id=new.id).count() == 0


def test_the_original_trip_is_not_changed(setup, sessions):  # noqa: F811
    c, auth, trip_id = setup
    _fill(sessions, trip_id)
    ingest(c, auth, trip_id, [offer("89.90")])
    before = _snapshot(sessions, trip_id)
    _post_copy(c, trip_id)
    assert _snapshot(sessions, trip_id) == before


def test_a_request_without_the_csrf_token_is_refused(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    assert c.post(f"/trips/{trip_id}/copy", follow_redirects=False).status_code == 403
    assert _copies_of(sessions, "Köln – München (copy)") == []


def test_the_edit_page_of_a_trip_has_the_copy_button(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    assert f'action="/trips/{trip_id}/copy"' in c.get(f"/trips/{trip_id}/edit").text
