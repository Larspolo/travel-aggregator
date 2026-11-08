"""The target price of a trip (#846): stored on the form, kept by a copy, in the export and in the import."""

import copy
from decimal import Decimal

from app.models import Trip
from app.trip_import import import_trip
from app.web.export import trip_export
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)


def _form(c, trip_id=None, target="80"):
    url = "/trips/new" if trip_id is None else f"/trips/{trip_id}/edit"
    data = {"title": "Wien – Graz", "status": "planning", "travelers": "1", "target_price": target,
            "csrf_token": _csrf(c, "/settings")}
    return c.post(url, data=data, follow_redirects=False)


def _target(sessions, title):
    with sessions() as s:
        return [t.target_price for t in s.query(Trip).filter(Trip.title == title).all()]


def test_a_new_trip_stores_the_target(setup, sessions):  # noqa: F811
    c, _, _ = setup
    assert _form(c, target="80").status_code == 303
    assert _target(sessions, "Wien – Graz") == [Decimal("80")]


def test_an_empty_target_stores_none(setup, sessions):  # noqa: F811
    c, _, _ = setup
    assert _form(c, target="").status_code == 303
    assert _target(sessions, "Wien – Graz") == [None]


def test_zero_and_text_are_refused(setup, sessions):  # noqa: F811
    c, _, _ = setup
    assert _form(c, target="0").status_code == 422
    assert _form(c, target="abc").status_code == 422
    assert _target(sessions, "Wien – Graz") == []


def test_the_edit_page_shows_the_stored_target_and_copy_keeps_it(setup, sessions):  # noqa: F811
    c, _, trip_id = setup
    with sessions() as s:
        s.get(Trip, trip_id).target_price = Decimal("64.50")
        s.commit()
    assert 'value="64.50"' in c.get(f"/trips/{trip_id}/edit").text
    r = c.post(f"/trips/{trip_id}/copy", headers={"X-CSRF-Token": _csrf(c, "/settings")}, follow_redirects=False)
    assert r.status_code == 303
    assert _target(sessions, "Köln – München (copy)") == [Decimal("64.50")]


def test_the_export_has_the_target_and_an_import_gives_it_back(sessions):
    with sessions() as s:
        trip = Trip(title="Export", target_price=Decimal("80.00"))
        s.add(trip)
        s.commit()
        data = trip_export(trip)
    assert data["trip"]["target_price"] == "80.00"
    with sessions() as s:
        result = import_trip(s, copy.deepcopy(data))
        s.commit()
        new = s.get(Trip, result.trip_id)
        assert new.target_price == Decimal("80.00")


def test_an_older_export_without_the_target_imports_none(sessions):
    with sessions() as s:
        trip = Trip(title="Old export", target_price=Decimal("80.00"))
        s.add(trip)
        s.commit()
        data = trip_export(trip)
    del data["trip"]["target_price"]
    with sessions() as s:
        result = import_trip(s, data)
        s.commit()
        assert s.get(Trip, result.trip_id).target_price is None
