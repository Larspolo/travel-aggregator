"""The edit page and the trip page hide the same names from the transfer places (#1482, epic #1457)."""

import html
import re
from types import SimpleNamespace

from app.models import Trip
from app.split_suggest import split_skip
from tests.test_split_suggest_page import _edit
from tests.test_split_suggest_page import _via as _via_offer
from tests.test_trip_filters_whole import PASS, itinerary
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)


def _trip_page(client, trip_id):
    return html.unescape(client.get(f"/trips/{trip_id}").text)


def _shown_via(page):
    """The names of the paragraph "Transfer places of these offers" on the trip page."""
    m = re.search(r'<p class="via-places">(.*?)</p>', page, re.S)
    text = m.group(1).split(":", 1)[1] if m else ""
    return [name.strip() for name in re.findall(r"([^·<>]+?) \(\d+\)", text)]


def _edit_options(page):
    m = re.search(r'<datalist id="via-places">(.*?)</datalist>', page, re.S)
    return re.findall(r'<option value="([^"]*)">', m.group(1)) if m else []


def test_origin_destination_and_their_alternatives_do_not_show(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    with sessions() as s:
        t = s.get(Trip, trip_id)
        t.origin_alt_text = "Utrecht, Rotterdam"
        t.destination_alt_text = "Basel"
        s.commit()
    ingest(client, auth, trip_id, [
        _via_offer("ICE 1", "Utrecht"),
        _via_offer("ICE 2", " rotterdam"),
        _via_offer("ICE 3", "Basel"),
        _via_offer("ICE 4", "Köln Hbf"),
        itinerary("D 1", "90", PASS),
    ])
    edit = _edit(client, trip_id)
    assert _edit_options(edit) == ["Köln Hbf"]
    assert "Split via Köln Hbf" in edit
    assert "Split via Utrecht" not in edit and "Split via Basel" not in edit
    assert _shown_via(_trip_page(client, trip_id)) == ["Köln Hbf"]


def test_split_skip_matches_a_part_origin_case_insensitively():
    trip_obj = SimpleNamespace(
        origin_text="Amsterdam", destination_text="Zürich", origin_alt_text=None, destination_alt_text=None,
        split_trips=[SimpleNamespace(origin_text="amsterdam", destination_text="Utrecht")])
    assert "Utrecht" in split_skip(trip_obj)
    assert "Amsterdam" in split_skip(trip_obj)
