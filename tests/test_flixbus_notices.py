"""The messages of a Flixbus connection are notices of the whole connection (#2760)."""

import copy
import json
from pathlib import Path

from app.parsers.flixbus import FlixbusParser
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

FIX = Path(__file__).parent / "fixtures" / "flixbus.com"
TRANSFER_TEXT = "Please transfer to the train station to reach your FlixTrain. Follow the posted signs."


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def fixture_offers():
    return FlixbusParser().parse(load("search-amsterdam-berlin.json")).offers


def test_the_transfer_message_is_a_low_notice_of_the_whole_connection():
    o = [o for o in fixture_offers() if o.fare_name == "Transfer"][0]
    assert [(n.text, n.level, n.leg) for n in o.notices] == [(TRANSFER_TEXT, "low", None)]


def test_a_connection_with_empty_messages_has_no_notices():
    offers = fixture_offers()
    others = [o for o in offers if o.fare_name != "Transfer"]
    assert len(others) == 2
    assert all(o.notices == [] for o in others)


def test_no_messages_key_keeps_the_stored_notices():
    raw = copy.deepcopy(load("search-amsterdam-berlin.json"))
    for t in raw["response"]["trips"]:
        for conn in t["results"].values():
            conn.pop("messages", None)
    assert all(o.notices is None for o in FlixbusParser().parse(raw).offers)


def test_a_non_list_messages_value_keeps_the_stored_notices():
    raw = copy.deepcopy(load("search-amsterdam-berlin.json"))
    for t in raw["response"]["trips"]:
        for conn in t["results"].values():
            conn["messages"] = "not a list"
    assert all(o.notices is None for o in FlixbusParser().parse(raw).offers)


def test_an_empty_text_is_skipped_and_a_long_text_is_cut_to_300():
    raw = copy.deepcopy(load("search-amsterdam-berlin.json"))
    conn = list(raw["response"]["trips"][0]["results"].values())[0]
    conn["messages"] = ["   ", "", "x" * 400]
    o = FlixbusParser().parse(raw).offers[0]
    assert [(len(n.text), n.level, n.leg) for n in o.notices] == [(300, "low", None)]


def test_the_version_is_1_4_0():
    assert FlixbusParser.version == "1.4.0"


def test_the_trip_page_shows_the_transfer_message_in_the_expanded_row(trip):  # noqa: F811
    client, auth, trip_id = trip
    offers = [o.model_dump(mode="json") for o in fixture_offers()]
    assert post(client, auth, trip_id, offers)["created"] == 3
    page = client.get(f"/trips/{trip_id}").text
    assert f'<div class="notices"><p>{TRANSFER_TEXT}</p></div>' in page
    assert "badge notice" not in page
