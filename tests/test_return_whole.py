"""The whole round-trip feature (#343): two linked trips, offers through the ingest API, the trips list and the journey
box of both trip pages. The journey box picks the pinned outbound offer, not the cheapest one."""

import re
from decimal import Decimal

from app.models import Itinerary, Trip
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)
from tests.test_trip_page import ingest, offer

OUT_DAY = "2026-12-20"
RET_DAY = "2026-12-27"


def _late(price, service_no, day=RET_DAY):
    o = offer(price, service_no)
    for leg in o["legs"]:
        leg["depart_at"] = day + leg["depart_at"][10:]
        leg["arrive_at"] = day + leg["arrive_at"][10:]
    return o


def _edit(c, sessions, trip_id, date_from, date_to):
    """The edit form of a trip: the dates are set, the other fields keep their values."""
    with sessions() as s:
        t = s.get(Trip, trip_id)
        data = {"title": t.title, "origin_text": t.origin_text or "", "destination_text": t.destination_text or "",
                "travelers": str(t.travelers or 1), "status": "planning", "date_from": date_from,
                "date_to": date_to, "notes": ""}
    r = c.post(f"/trips/{trip_id}/edit", data=data, headers={"X-CSRF-Token": _csrf(c, "/settings")},
               follow_redirects=False)
    assert r.status_code == 303


def _pin(c, sessions, trip_id, price):
    with sessions() as s:
        it_id = next(it.id for it in s.query(Itinerary).filter_by(trip_id=trip_id)
                     if min(f.latest_price for f in it.fares) == Decimal(price))
    r = c.post(f"/trips/{trip_id}/itineraries/{it_id}/pin", headers={"X-CSRF-Token": _csrf(c, "/settings")},
               follow_redirects=False)
    assert r.status_code == 303


def _box(c, trip_id):
    page = c.get(f"/trips/{trip_id}").text
    start = page.find('<section class="journey"')
    return page[start:page.index("</section>", start)] if start >= 0 else ""


def _total(box):
    """The total effective cost of the box, and the effective cost of each direction, shown in the box."""
    costs = [Decimal(x) for x in re.findall(r"(?<!Total )effective cost €([\d.]+)", box)]
    total = Decimal(re.search(r"Total effective cost €([\d.]+)", box).group(1))
    return total, costs


def test_a_round_trip_from_the_ingest_to_the_journey_box(setup, sessions):  # noqa: F811
    c, auth, out = setup
    _edit(c, sessions, out, OUT_DAY, OUT_DAY)
    r = c.post(f"/trips/{out}/return", headers={"X-CSRF-Token": _csrf(c, "/settings")}, follow_redirects=False)
    assert r.status_code == 303
    with sessions() as s:
        ret = s.query(Trip).filter_by(return_of_id=out).one().id
    _edit(c, sessions, ret, RET_DAY, RET_DAY)

    ingest(c, auth, out, [offer("89.90", "ICE 105"), offer("99.90", "ICE 123"), offer("119.90", "ICE 131")])
    ingest(c, auth, ret, [_late("40.00", "ICE 901"), _late("50.00", "ICE 902"), _late("60.00", "ICE 903")])
    _pin(c, sessions, out, "119.90")  # the most expensive outbound offer is pinned

    # the trips list: the return trip follows its outbound trip, and the journey total is the two best prices
    html = c.get("/").text
    assert html.index("Köln – München</a></h2>") < html.index("Return of Köln – München")
    assert "Journey price total: EUR 129.90" in html

    # the journey box of both trip pages: the pinned outbound offer, the cheapest return offer, one total
    boxes = {page_id: _box(c, page_id) for page_id in (out, ret)}
    for page_id, box in boxes.items():
        assert f'href="/trips/{out}"' in box and f'href="/trips/{ret}"' in box
        assert "EUR 119.90" in box and "EUR 89.90" not in box
        assert "EUR 40.00" in box and "EUR 50.00" not in box and "EUR 60.00" not in box
        assert "departs before" not in box
        total, costs = _total(box)
        assert len(costs) == 2 and total == sum(costs)
    assert _total(boxes[out]) == _total(boxes[ret])
