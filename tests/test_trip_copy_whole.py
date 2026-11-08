"""Copy trip and copy journey (#800): the whole feature in the trips list. The copy of a one-way trip is one line with
no offers, the copy of a journey is one chain of 3, and the original trips do not change."""

from app.models import Trip
from app.trips import in_journeys, list_trips
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_copy_journey import _journey
from tests.test_trip_page import ingest, offer


def _post(c, path):
    return c.post(path, headers={"X-CSRF-Token": _csrf(c, "/settings")}, follow_redirects=False)


def test_the_copies_of_a_trip_and_a_journey_show_in_the_list(setup, sessions):  # noqa: F811
    c, auth, journey_first = setup
    with sessions() as s:
        one_way = Trip(title="Amsterdam – Zürich", origin_text="Amsterdam", destination_text="Zürich")
        s.add(one_way)
        s.commit()
        one_way_id = one_way.id
    journey_ids = _journey(sessions, journey_first)
    ingest(c, auth, one_way_id, [offer("49.00")])
    ingest(c, auth, journey_first, [offer("89.90")])

    with sessions() as s:
        originals = [(t.title, t.return_of_id) for t in (s.get(Trip, i) for i in [one_way_id, *journey_ids])]

    assert _post(c, f"/trips/{one_way_id}/copy").status_code == 303
    assert _post(c, f"/trips/{journey_first}/copy-journey").status_code == 303

    with sessions() as s:
        lines = in_journeys(list_trips(s))
        assert [(t.title, t.return_of_id) for t in (s.get(Trip, i) for i in [one_way_id, *journey_ids])] == originals

    copy_lines = [(kind, row.title) for kind, row, _ in lines if kind != "total" and row.title.endswith("(copy)")]
    assert copy_lines == [
        ("trip", "Amsterdam – Zürich (copy)"),
        ("trip", "Köln – München (copy)"),
        ("next", "München – Wien (copy)"),
        ("next", "Wien – Köln (copy)"),
    ]
    # the one-way copy is a single line: no later line of its own chain
    rows = {r.title: r for _, r, _ in lines}
    assert rows["Amsterdam – Zürich (copy)"].offer_count == 0
    assert rows["Köln – München (copy)"].offer_count == 0
    assert rows["München – Wien (copy)"].offer_count == 0
    assert rows["Wien – Köln (copy)"].offer_count == 0
    assert rows["Amsterdam – Zürich"].offer_count == 1
    assert rows["Köln – München"].offer_count == 1

    page = c.get("/")
    assert page.status_code == 200
    for title in ["Amsterdam – Zürich (copy)", "Köln – München (copy)", "München – Wien (copy)", "Wien – Köln (copy)"]:
        assert title in page.text
