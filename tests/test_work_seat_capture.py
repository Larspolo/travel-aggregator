"""The work seat with captured payloads (#2568, epic #2565): a bahn.de ICE leg with Wi-Fi and power sockets gets the part
on the trip page, and a FlixBus leg with no amenities gets none."""

import copy
import json
from pathlib import Path

from app import tokens
from tests.test_trip_booked import trip  # noqa: F401 (fixture)

FIX = Path(__file__).parent / "fixtures"
BAHN = FIX / "bahn.de" / "fahrplan-amsterdam-zuerich.json"
FLIX = FIX / "flixbus.com" / "search-amsterdam-paris.json"


def post_raw(client, auth, trip_id, source, version, raw):
    body = {"trip_id": trip_id, "source": source, "parser_version": version,
            "captured_at": "2026-11-03T19:41:00Z", "raw": raw}
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text


def bahn_with_power():
    """The fixture's ICE 105 leg says wifi (WV) only: add the power sockets (LS) to it, as a real leg may say."""
    raw = json.loads(BAHN.read_text(encoding="utf-8"))
    for conn in raw["response"]["verbindungen"]:
        for a in conn["verbindungsAbschnitte"]:
            if a["verkehrsmittel"].get("name") == "ICE 105":
                a["verkehrsmittel"]["zugattribute"].append({"kategorie": "INFORMATION", "key": "LS", "value": "power"})
    return raw


def flix_without_amenities():
    raw = copy.deepcopy(json.loads(FLIX.read_text(encoding="utf-8")))
    for trip_ in raw["response"]["trips"]:
        results = trip_["results"]
        for conn in results.values() if isinstance(results, dict) else results:
            for leg in conn["legs"]:
                leg["amenities"] = []
    return raw


def _token(sessions):
    with sessions() as s:
        return {"Authorization": f"Bearer {tokens.create(s, 'seat')}"}


def test_the_bahn_ice_leg_with_wifi_and_power_gets_the_work_seat_part(trip, sessions):  # noqa: F811
    client, trip_id = trip
    post_raw(client, _token(sessions), trip_id, "bahn.de", "1.4.0", bahn_with_power())
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "15", "work_seat_hour_markup": "5"}).text
    # 336 minutes × (5 − 15) / 60 = −56 euro
    assert "€-56 work seat" in page
    assert "work seat" not in client.get(f"/trips/{trip_id}", params={"hour_markup": "15"}).text


def test_a_flixbus_leg_with_no_amenities_gets_no_work_seat_part(trip, sessions):  # noqa: F811
    client, trip_id = trip
    post_raw(client, _token(sessions), trip_id, "flixbus.com", "1.0.0", flix_without_amenities())
    page = client.get(f"/trips/{trip_id}", params={"hour_markup": "15", "work_seat_hour_markup": "5"}).text
    assert "work seat" not in page

