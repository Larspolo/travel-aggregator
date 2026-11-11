"""The "Copy summary" section of the trip page (#2162)."""

import html
import re

from app.models import Itinerary
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def _section(page):
    return re.search(r'<section class="trip-summary[^"]*" id="trip-summary".*?</section>', page, re.S).group(0)


def test_a_trip_with_4_rows_has_the_button_and_the_3_lines(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("80.00", "ICE 1"), offer("90.00", "ICE 2"),
                                   offer("100.00", "ICE 3"), offer("200.00", "ICE 4")])
    section = _section(client.get(f"/trips/{trip_id}").text)
    assert 'type="button"' in section and "Copy summary" in section and 'role="status"' in section
    text = html.unescape(re.search(r"<textarea[^>]*readonly[^>]*hidden[^>]*>(.*?)</textarea>", section, re.S).group(1))
    lines = text.split("\n")
    assert len(lines) == 3
    assert "€80.00" in lines[0] and "€100.00" in lines[2] and "€200.00" not in text


def test_the_page_loads_the_script(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("80.00")])
    assert '<script src="/static/copy_summary.js" defer></script>' in client.get(f"/trips/{trip_id}").text
    assert "writeText" in client.get("/static/copy_summary.js").text


def test_a_trip_with_no_rows_shows_no_button(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    assert "Copy summary" not in client.get(f"/trips/{trip_id}").text
    ingest(client, auth, trip_id, [offer("80.00")])
    with sessions() as s:
        it_id = s.query(Itinerary).filter_by(trip_id=trip_id).one().id
    page = client.get(f"/trips/{trip_id}?mode=bus").text  # a filter hides the only row
    assert it_id and "Copy summary" not in page


def test_the_htmx_table_has_the_section_out_of_band(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("80.00")])
    r = client.get(f"/trips/{trip_id}", headers={"HX-Request": "true"})
    assert re.search(r'id="trip-summary" hx-swap-oob="true"', r.text)
