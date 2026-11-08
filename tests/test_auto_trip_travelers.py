"""With "auto-select trip" (`auto_trip`), a capture for another number of travelers than the trip gives the travelers
warning, not "No trip matches" (owner check of #945, 2026-11-08: a bahn.de search for 1 adult into a trip for 2 showed
"No trip matches: + new trip"). The trip matches the places and the date, so a new trip is no help."""

from tests.test_capture_mismatch import _setup
from tests.test_trip_travelers import WARNING_1_OF_2, _raw, _set_travelers


def _ingest(c, auth, trip_id, raw, **extra):
    r = c.post("/api/ingest", headers=auth, json={"trip_id": trip_id, "source": "bahn.de", "parser_version": "0.0.1",
                                                  "captured_at": "2026-11-03T19:41:00Z", "raw": raw, **extra})
    assert r.status_code < 300, r.text
    return r.json()


def test_a_travelers_mismatch_with_auto_trip_gives_the_warning_and_no_suggestion(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    _set_travelers(sessions, trip_id, 2)
    r = _ingest(c, auth, trip_id, _raw(travelers=1), auto_trip=True)
    assert r["trip_id"] == trip_id
    assert r["suggestion"] is None
    assert r["warning"] == WARNING_1_OF_2
    assert r["mismatch"] == "travelers"


def test_a_places_mismatch_with_auto_trip_still_gives_a_suggestion(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="Hamburg")
    r = _ingest(c, auth, trip_id, _raw(), auto_trip=True)
    assert r["suggestion"] is not None
    assert r["mismatch"] == "places"


def test_no_mismatch_gives_mismatch_none(sessions, monkeypatch):
    c, auth, trip_id = _setup(sessions, monkeypatch, destination="München")
    r = _ingest(c, auth, trip_id, _raw(), auto_trip=True)
    assert (r["mismatch"], r["warning"], r["suggestion"]) == (None, None, None)
