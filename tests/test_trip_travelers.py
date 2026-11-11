"""A capture for another number of travelers than the trip gives the warning "travelers" (#765)."""

import json
from pathlib import Path

from sqlalchemy import select

from app import ingest
from app.models import Capture, Trip
from app.tripmatch import mismatch
from tests.test_capture_mismatch import _setup
from tests.test_tripmatch import offer, trip

BAHN = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen.json"
WARNING_1_OF_2 = "These offers are for 1 traveler; the trip has 2"


def _raw(travelers=None):
    raw = json.loads(BAHN.read_text(encoding="utf-8"))
    if travelers is not None:
        raw["request"]["reisende"][0]["anzahl"] = travelers
    return raw


def _ingest(c, auth, trip_id, raw):
    r = c.post("/api/ingest", headers=auth, json={"trip_id": trip_id, "source": "bahn.de", "parser_version": "0.0.1",
                                                  "captured_at": "2026-11-03T19:41:00Z", "raw": raw})
    assert r.status_code < 300, r.text
    return r.json()


def _set_travelers(sessions, trip_id, travelers):
    with sessions() as s:
        s.get(Trip, trip_id).travelers = travelers
        s.commit()


def _capture(sessions, trip_id):
    with sessions() as s:
        return s.scalar(select(Capture).where(Capture.trip_id == trip_id))


def test_one_traveler_into_a_trip_for_two_stores_the_reason(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    _set_travelers(sessions, trip_id, 2)
    assert _ingest(c, auth, trip_id, _raw(travelers=1))["warning"] == WARNING_1_OF_2
    assert _capture(sessions, trip_id).mismatch == "travelers"


def test_the_captures_pages_show_the_travelers_warning(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    _set_travelers(sessions, trip_id, 2)
    _ingest(c, auth, trip_id, _raw(travelers=1))
    assert WARNING_1_OF_2 in c.get(f"/trips/{trip_id}/captures").text
    assert WARNING_1_OF_2 in c.get("/captures").text


def test_two_travelers_into_a_trip_for_two_show_no_warning(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    _set_travelers(sessions, trip_id, 2)
    assert _ingest(c, auth, trip_id, _raw(travelers=2))["warning"] is None
    assert _capture(sessions, trip_id).mismatch is None


def test_a_capture_with_no_count_shows_no_warning(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    _set_travelers(sessions, trip_id, 2)
    raw = json.loads(BAHN.read_text(encoding="utf-8"))["response"]
    assert _ingest(c, auth, trip_id, raw)["warning"] is None
    assert _capture(sessions, trip_id).travelers is None
    assert _capture(sessions, trip_id).mismatch is None


def test_a_wrong_place_still_shows_the_place_warning_first(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="Lisboa")
    _set_travelers(sessions, trip_id, 2)
    assert _ingest(c, auth, trip_id, _raw(travelers=1))["warning"] == "These offers do not match the trip (places)"


def test_moving_to_a_trip_with_the_same_travelers_removes_the_warning(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    _set_travelers(sessions, trip_id, 2)
    _ingest(c, auth, trip_id, _raw(travelers=1))
    with sessions() as s:
        other = Trip(title="Köln – München (2)", origin_text="Köln", destination_text="München", travelers=1)
        s.add(other)
        s.commit()
        other_id = other.id
    with sessions() as s:
        cap = s.scalar(select(Capture).where(Capture.trip_id == trip_id))
        ingest.move_capture(s, cap, other_id)
    with sessions() as s:
        assert s.get(Capture, _capture(sessions, other_id).id).mismatch is None


def test_mismatch_gives_travelers_only_with_a_count_that_differs():
    one = trip()
    one.travelers = 1
    assert mismatch(one, [offer()], travelers=1) is None
    assert mismatch(one, [offer()], travelers=None) is None
    t = trip()
    t.travelers = 2
    assert mismatch(t, [offer()], travelers=1) == "travelers"
    assert mismatch(t, [offer()], travelers=2) is None
    assert mismatch(t, [offer(to_name="Lisboa Oriente")], travelers=1) == "places"
