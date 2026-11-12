"""The expected load markup with a captured bahn.de payload (#2610, epic #2607): the Köln → München fixture gives
the load of its legs, the trip page shows the load part with the markup, and no markup changes no cost."""

import json
from pathlib import Path

from app import tokens
from tests.test_trip_booked import trip  # noqa: F401 (fixture)

FIX = Path(__file__).parent / "fixtures" / "bahn.de" / "fahrplan-koeln-muenchen.json"


def koeln_muenchen():
    """The fixture's ICE 611 connection has no price: copy the price of the first connection (as tests/test_leg_load.py)."""
    raw = json.loads(FIX.read_text(encoding="utf-8"))
    conns = raw["response"]["verbindungen"]
    conns[1]["angebotsPreis"] = conns[0]["angebotsPreis"]
    conns[1].pop("risNotizen")  # #2629: with the cancel notice the connection is no offer
    return raw


def _auth(sessions):
    with sessions() as s:
        return {"Authorization": f"Bearer {tokens.create(s, 'load')}"}


def _post(client, auth, trip_id, raw):
    body = {"trip_id": trip_id, "source": "bahn.de", "parser_version": "1.4.0",
            "captured_at": "2026-11-08T09:00:00Z", "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text


def test_the_second_class_fare_with_two_level_3_legs_adds_both_markups(trip, sessions):  # noqa: F811
    client, trip_id = trip
    _post(client, _auth(sessions), trip_id, koeln_muenchen())
    page = client.get(f"/trips/{trip_id}", params={"load_very_high_markup": "8"}).text
    # IC 2048 and ICE 613 are level 3 in 2nd class: 2 × €8. ICE 611 (no class) is level 3: €8.
    assert "€16 expected load very high" in page
    assert "€8 expected load very high" in page


def test_the_first_class_fare_of_ice_519_adds_no_load_part(trip, sessions):  # noqa: F811
    client, trip_id = trip
    _post(client, _auth(sessions), trip_id, koeln_muenchen())
    page = client.get(f"/trips/{trip_id}", params={"load_very_high_markup": "8", "load_high_markup": "3"}).text
    # ICE 519 is 2nd class fully booked, but the 1st class fare uses the 1st class load (none).
    assert "2nd class fully booked" in page
    assert "€8 expected load fully booked" not in page


def test_without_a_load_markup_no_breakdown_part_is_shown(trip, sessions):  # noqa: F811
    client, trip_id = trip
    _post(client, _auth(sessions), trip_id, koeln_muenchen())
    page = client.get(f"/trips/{trip_id}").text
    assert "expected load very high" not in page


def test_a_connection_without_load_shows_no_badge_and_no_part(trip, sessions):  # noqa: F811
    client, trip_id = trip
    raw = koeln_muenchen()
    for conn in raw["response"]["verbindungen"]:
        for a in conn["verbindungsAbschnitte"]:
            a["auslastungsmeldungen"] = [{"klasse": "KLASSE_1", "stufe": 0}, {"klasse": "KLASSE_2", "stufe": 0}]
    _post(client, _auth(sessions), trip_id, raw)
    page = client.get(f"/trips/{trip_id}", params={"load_very_high_markup": "8", "load_high_markup": "3"}).text
    assert 'class="badge leg-load"' not in page
    assert "expected load very high" not in page
