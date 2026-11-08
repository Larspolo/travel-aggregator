"""The whole multi-city feature (#559): four linked trips, one offer each, the trips list, the journey box of each
trip page, a delete of a middle trip and the archive of the journey as a whole."""

from app.models import Trip
from tests.test_reparse import _csrf, setup  # noqa: F401  (fixture: logged-in client)
from tests.test_return_whole import _total
from tests.test_trip_journey import _box
from tests.test_trip_next import _next, _set_places
from tests.test_trip_page import ingest, offer

DAYS = ["2026-12-20", "2026-12-22", "2026-12-24", "2026-12-26"]


def _on(price, service_no, day):
    o = offer(price, service_no)
    for leg in o["legs"]:
        leg["depart_at"] = day + leg["depart_at"][10:]
        leg["arrive_at"] = day + leg["arrive_at"][10:]
    return o


def _csrf_header(c):
    return {"X-CSRF-Token": _csrf(c, "/settings")}


def _status(sessions, trip_id, status):
    with sessions() as s:
        s.get(Trip, trip_id).status = status
        s.commit()


def test_a_journey_of_four_trips_from_the_ingest_to_the_archive(setup, sessions):  # noqa: F811
    c, auth, first = setup
    _set_places(sessions, first, "Amsterdam", "Berlin")

    # 1. three times "Add next trip" from the last trip: four linked trips in sequence
    ids = [first]
    for city in ("Hamburg", "Hannover", "Leipzig"):
        new = _next(c, ids[-1])
        ids.append(new)
        with sessions() as s:
            s.get(Trip, new).destination_text = city
            s.commit()
    with sessions() as s:
        assert [s.get(Trip, i).return_of_id for i in ids] == [None, *ids[:-1]]
    trips = ids

    # 2. one offer per trip, each later than the previous one; the third trip departs before the second arrives
    ingest(c, auth, trips[0], [_on("89.90", "ICE 105", DAYS[0])])
    ingest(c, auth, trips[1], [_on("50.00", "ICE 200", DAYS[1])])
    ingest(c, auth, trips[2], [_on("30.00", "ICE 300", DAYS[1])])
    ingest(c, auth, trips[3], [_on("20.00", "ICE 400", DAYS[3])])

    # 3. the trips list: the four trips together, in sequence, with the sum of the four best offers
    html = c.get("/").text
    positions = [html.index(f"/trips/{t}") for t in trips]
    assert positions == sorted(positions)
    assert html.count("Journey price total") == 1
    assert "Journey price total: EUR 189.90" in html

    # 4. the journey box of each trip page
    for page_id in trips:
        box = _box(c, page_id)
        for t in trips:
            assert f'href="/trips/{t}"' in box
        assert "€89.90" in box and "€50.00" in box and "€30.00" in box and "€20.00" in box
        total, costs = _total(box)
        assert len(costs) == 4 and total == sum(costs)  # the effective cost also counts the hour and transfer weights
        assert box.count("departs before the previous part arrives") == 1
        part3 = box[box.index("<strong>Part 3"):]
        assert "departs before the previous part arrives" in part3.split("</li>")[0]

    # 5. delete the second trip: the other three stay linked in sequence
    r = c.post(f"/trips/{trips[1]}/delete", headers=_csrf_header(c), follow_redirects=False)
    assert r.status_code in (302, 303)
    rest = [trips[0], trips[2], trips[3]]
    with sessions() as s:
        assert s.get(Trip, trips[1]) is None
        assert [s.get(Trip, i).return_of_id for i in rest] == [None, trips[0], trips[2]]
    html = c.get("/").text
    positions = [html.index(f"/trips/{t}") for t in rest]
    assert positions == sorted(positions)
    for page_id in rest:
        box = _box(c, page_id)
        for t in rest:
            assert f'href="/trips/{t}"' in box
        assert f'href="/trips/{trips[1]}"' not in box
        assert len(_total(box)[1]) == 3

    # 6. archive the journey: it moves to the archived list as a whole
    for t in rest:
        _status(sessions, t, "archived")
    assert "Journey price total" not in c.get("/").text
    archived = c.get("/?archived=1").text
    for t in rest:
        assert f"/trips/{t}" in archived
    assert "No archived trips" not in archived
