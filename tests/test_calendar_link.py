"""The "Add to calendar" link of a booked row of the trip page (#781)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Itinerary, Trip
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _itinerary(sessions, trip_id):
    with sessions() as s:
        return s.query(Itinerary).filter_by(trip_id=trip_id).one().id


def test_a_booked_row_downloads_a_calendar_file_with_one_event_per_leg(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    ingest(client, auth, tid, [offer("89.90")])
    iid = _itinerary(sessions, tid)
    url = f"/trips/{tid}/itineraries/{iid}/calendar.ics"
    assert url not in client.get(f"/trips/{tid}").text
    with sessions() as s:
        s.get(Itinerary, iid).booked = True
        s.commit()
    page = client.get(f"/trips/{tid}").text
    assert f'href="{url}" download' in page and "Add to calendar" in page
    r = client.get(url)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert r.headers["content-disposition"] == f'attachment; filename="trip-{tid}-amsterdam-zurich.ics"'
    assert r.text.count("BEGIN:VEVENT") == 2


def test_an_itinerary_of_another_trip_is_404(trip, sessions):  # noqa: F811
    client, auth, tid = trip
    ingest(client, auth, tid, [offer("89.90")])
    iid = _itinerary(sessions, tid)
    with sessions() as s:
        other = Trip(title="Other", origin_text="A", destination_text="B")
        s.add(other)
        s.commit()
        oid = other.id
    assert client.get(f"/trips/{oid}/itineraries/{iid}/calendar.ics").status_code == 404


@pytest.mark.usefixtures("sessions")
def test_no_login_goes_to_the_login_page():
    r = TestClient(app).get("/trips/1/itineraries/1/calendar.ics", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


@pytest.mark.slow
@pytest.mark.parametrize("width", [1280, 390])
def test_the_link_fits_next_to_the_row_actions(trip, sessions, tmp_path, width):  # noqa: F811
    from playwright.sync_api import sync_playwright

    from tests.test_all_pages_look import _launch, _serve

    client, auth, tid = trip
    ingest(client, auth, tid, [offer("89.90")])
    with sessions() as s:
        s.get(Itinerary, _itinerary(sessions, tid)).booked = True
        s.commit()
    server, thread, base = _serve()
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            page = browser.new_page(viewport={"width": width, "height": 844})
            page.goto(f"{base}/trips/{tid}")
            boxes = page.eval_on_selector_all("td.actions > a.icon, td.actions button.icon, td.actions .pick",
                                              "els => els.map(e => { const r = e.getBoundingClientRect();"
                                              " return [r.left, r.right, r.top, r.bottom]; })")
            scroll = page.evaluate("document.documentElement.scrollWidth - innerWidth")
            page.screenshot(path=str(tmp_path / f"calendar-link-{width}.png"), full_page=True)
            browser.close()
    finally:
        server.should_exit = True
        thread.join(5)
    assert scroll <= 0 and len(boxes) == 5
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[1] <= b[0] or b[1] <= a[0] or a[3] <= b[2] or b[3] <= a[2], (a, b)
