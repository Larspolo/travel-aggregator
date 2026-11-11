"""Each fare of the trip page links to the page address of the capture of its newest price (#2078)."""

from sqlalchemy import select

from fastapi.testclient import TestClient

from app.main import app
from app.models import Capture, FarePrice
from tests.test_share import share
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

URL = "https://www.bahn.de/buchung/fahrplan/suche#sts=true"


def _set_url(sessions, url):
    with sessions() as s:
        for cap in s.scalars(select(Capture)):
            cap.page_url = url
        s.commit()


def _link(page):
    return page.split("Open search")[0].rsplit("<a ", 1)[1] if "Open search" in page else None


def test_a_fare_shows_the_address_of_its_capture(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90", "ICE 105")])
    _set_url(sessions, URL)
    page = client.get(f"/trips/{trip_id}").text
    link = _link(page)
    assert link is not None
    assert f'href="{URL}"' in link and 'rel="noopener noreferrer"' in link and 'target="_blank"' in link
    assert page.count("Open search") == 1


def test_no_link_for_no_address_a_deleted_capture_or_a_bad_scheme(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90", "ICE 105")])
    for url in (None, "javascript:alert(1)"):
        _set_url(sessions, url)
        assert "Open search" not in client.get(f"/trips/{trip_id}").text
    _set_url(sessions, URL)
    with sessions() as s:
        for p in s.scalars(select(FarePrice)):
            p.capture_id = None
        s.commit()
    assert "Open search" not in client.get(f"/trips/{trip_id}").text


def test_a_manual_fare_shows_no_link(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90", "ICE 105")])
    _set_url(sessions, URL)
    with sessions() as s:
        for p in s.scalars(select(FarePrice)):
            p.fare.source = "manual"
            p.capture_id = None  # a manual price has no capture
        s.commit()
    assert "Open search" not in client.get(f"/trips/{trip_id}").text


def test_the_shared_page_shows_no_link(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90", "ICE 105")])
    _set_url(sessions, URL)
    page = TestClient(app).get(share(client, trip_id)).text
    assert "Open search" not in page and "bahn.de/buchung" not in page
