"""The journey box shows all parts of a multi-city journey (#562)."""

from tests.test_reparse import setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_journey import _box, _late
from tests.test_trip_next import _next
from tests.test_trip_page import BODY, ingest, offer


def test_a_chain_of_three_shows_three_parts_and_the_total(setup, sessions):  # noqa: F811
    c, auth, first = setup
    second = _next(c, first)
    third = _next(c, second)
    ingest(c, auth, first, [offer("89.90", "ICE 105")])
    ingest(c, auth, second, [_late("50.00", "ICE 900")])
    ingest(c, auth, third, [_late("30.00", "ICE 901", day="2026-12-28")])
    for page_id in (first, second, third):
        box = _box(c, page_id)
        for t in (first, second, third):
            assert f'href="/trips/{t}"' in box
        assert "Part 1" in box and "Part 2" in box and "Part 3" in box and "Outbound" not in box
        assert "€89.90" in box and "€50.00" in box and "€30.00" in box
        assert "Total effective cost €" in box and "departs before" not in box


def test_a_part_that_departs_before_the_previous_arrival_shows_the_mark(setup, sessions):  # noqa: F811
    c, auth, first = setup
    second = _next(c, first)
    third = _next(c, second)
    ingest(c, auth, first, [offer("89.90", "ICE 105")])
    ingest(c, auth, second, [_late("50.00", "ICE 900")])
    ingest(c, auth, third, [_late("30.00", "ICE 901", day=BODY["offers"][0]["legs"][0]["depart_at"][:10])])
    box = _box(c, first)
    assert box.count("departs before the previous part arrives") == 1
    part3 = box[box.index("<strong>Part 3"):]
    assert "departs before the previous part arrives" in part3.split("</li>")[0]
