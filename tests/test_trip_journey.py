"""The journey box on the trip page of each direction (#342)."""

from decimal import Decimal

from app.models import Itinerary, Trip
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_page import BODY, ingest, offer


def _return(c, sessions, trip_id):
    c.post(f"/trips/{trip_id}/return", headers={"X-CSRF-Token": _csrf(c, "/settings")}, follow_redirects=False)
    with sessions() as s:
        return s.query(Trip).filter_by(return_of_id=trip_id).one().id


def _late(price, service_no, day="2026-12-21"):
    o = offer(price, service_no)
    for leg in o["legs"]:
        leg["depart_at"] = day + leg["depart_at"][10:]
        leg["arrive_at"] = day + leg["arrive_at"][10:]
    return o


def _set(sessions, trip_id, service_no, **flags):
    with sessions() as s:
        for it in s.query(Itinerary).filter_by(trip_id=trip_id):
            if any(leg.service_no == service_no for leg in it.legs):
                for k, v in flags.items():
                    setattr(it, k, v)
        s.commit()


def _box(c, trip_id):
    page = c.get(f"/trips/{trip_id}").text
    start = page.find('<section class="journey"')
    return page[start:page.index("</section>", start)] if start >= 0 else ""


def test_a_trip_with_no_link_shows_no_box(setup):  # noqa: F811
    c, auth, trip_id = setup
    ingest(c, auth, trip_id, [offer("89.90")])
    assert _box(c, trip_id) == ""


def test_the_box_shows_both_directions_and_the_total(setup, sessions):  # noqa: F811
    c, auth, trip_id = setup
    ret = _return(c, sessions, trip_id)
    ingest(c, auth, trip_id, [offer("89.90", "ICE 105")])
    assert "no offers yet" in _box(c, trip_id) and "Total effective cost" not in _box(c, trip_id)
    ingest(c, auth, ret, [_late("50.00", "ICE 900")])
    for page_id in (trip_id, ret):
        box = _box(c, page_id)
        assert f'href="/trips/{trip_id}"' in box and f'href="/trips/{ret}"' in box
        assert "€89.90" in box and "€50.00" in box and "Total effective cost €" in box
        assert "departs before" not in box
    total = box.split("Total effective cost €")[1].split("<")[0]
    assert Decimal(total) > Decimal("139.90")


def test_booked_wins_over_pinned_and_pinned_over_cheaper(setup, sessions):  # noqa: F811
    c, auth, trip_id = setup
    ret = _return(c, sessions, trip_id)
    ingest(c, auth, trip_id, [offer("50.00", "ICE 1"), offer("80.00", "ICE 2"), offer("120.00", "ICE 3")])
    ingest(c, auth, ret, [_late("40.00", "ICE 9")])
    assert "€50.00" in _box(c, ret)
    _set(sessions, trip_id, "ICE 2", pinned=True)
    assert "€80.00" in _box(c, ret) and "€50.00" not in _box(c, ret)
    _set(sessions, trip_id, "ICE 3", booked=True)
    assert "€120.00" in _box(c, ret) and "€80.00" not in _box(c, ret)
    _set(sessions, trip_id, "ICE 3", hidden=True)  # a hidden offer never counts
    assert "€80.00" in _box(c, ret)


def test_the_mark_shows_when_the_return_departs_before_the_outbound_arrives(setup, sessions):  # noqa: F811
    c, auth, trip_id = setup
    ret = _return(c, sessions, trip_id)
    ingest(c, auth, trip_id, [offer("89.90", "ICE 105")])
    ingest(c, auth, ret, [_late("50.00", "ICE 900", day=BODY["offers"][0]["legs"][0]["depart_at"][:10])])
    assert "The return departs before the outbound arrives" in _box(c, trip_id)


def test_the_sliders_change_only_the_present_direction(setup, sessions):  # noqa: F811
    c, auth, trip_id = setup
    ret = _return(c, sessions, trip_id)
    ingest(c, auth, trip_id, [offer("89.90", "ICE 105")])
    ingest(c, auth, ret, [_late("50.00", "ICE 900")])
    page = c.get(f"/trips/{trip_id}?hour_markup=0&transfer_markup=0").text
    start = page.index('<section class="journey"')
    box = page[start:page.index("</section>", start)]
    other = _box(c, ret)
    # the return line is the same on both pages; the outbound line changes with the slider
    ret_line = box[box.index("<strong>Return"):box.index("</li>", box.index("<strong>Return"))]
    assert ret_line in other
    out_line = box[box.index("<strong>Outbound"):box.index("</li>")]
    assert "effective cost €89.90" in out_line and out_line not in other
