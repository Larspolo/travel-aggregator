"""The transfer line of the trip page shows the platforms of the transfer (#2740)."""

import json
from decimal import Decimal
from pathlib import Path

from app.parsers.bahn import BahnParser
from app.parsers.oebb import OebbParser
from tests.test_oebb_parser import priced
from tests.test_leg_platforms_page import reserved
from tests.test_self_transfer import post
from tests.test_trip_page import trip  # noqa: F401  (trip is a fixture)

FIX = Path(__file__).parent / "fixtures"


def offers_of(result):
    out = []
    for o in result.offers:
        d = o.model_dump(mode="json")
        for f in d.get("fares") or []:
            if f.get("amount") is None:
                f["amount"] = str(Decimal("49.90"))
        out.append(d)
    return out


def page_of(trip, result):  # noqa: F811
    client, auth, trip_id = trip
    post(client, auth, trip_id, offers_of(result))
    return client.get(f"/trips/{trip_id}").text


def bahn(name):
    return BahnParser().parse(json.loads((FIX / "bahn.de" / name).read_text(encoding="utf-8")))


def transfers(page, place):
    return [line for line in page.split('<div class="transfer muted">')[1:] if place in line.split("</div>")[0]]


def test_koeln_muenchen_shows_platform_4_to_5_at_mannheim(trip):  # noqa: F811
    lines = transfers(page_of(trip, bahn("fahrplan-koeln-muenchen.json")), "Mannheim Hbf")
    assert any(" · platform 4 → 5" in line.split("</div>")[0] for line in lines)


def test_amsterdam_berlin_shows_same_platform_at_hannover(trip):  # noqa: F811
    lines = transfers(page_of(trip, bahn("fahrplan-amsterdam-berlin.json")), "Hannover Hbf")
    assert any(" · same platform" in line.split("</div>")[0] for line in lines)


def test_oebb_amsterdam_wien_shows_no_platform_at_salzburg(trip):  # noqa: F811
    lines = transfers(page_of(trip, OebbParser().parse(priced("search-amsterdam-wien.json"))), "Salzburg Hbf")
    assert lines
    assert not any("platform" in line.split("</div>")[0] for line in lines)


def test_a_change_of_station_shows_both_platforms(trip):  # noqa: F811
    a = reserved(None, None)["legs"][0]
    offer = reserved(None, None)
    first = dict(a, to_name="Berlin Hbf", to_platform="12")
    second = dict(a, from_name="Berlin Ostbahnhof", from_platform="3", seq=1)
    second["depart_at"], second["arrive_at"] = "2030-05-01T12:00:00+02:00", "2030-05-01T14:00:00+02:00"
    first["depart_at"], first["arrive_at"] = "2030-05-01T08:00:00+02:00", "2030-05-01T11:00:00+02:00"
    offer["legs"] = [first, second]
    client, auth, trip_id = trip
    post(client, auth, trip_id, [offer])
    page = client.get(f"/trips/{trip_id}").text
    assert "Change of station: Berlin Hbf → Berlin Ostbahnhof" in page
    assert " · platform 12 → 3" in page
