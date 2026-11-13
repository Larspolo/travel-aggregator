"""The transfer line of the shared page shows the platforms of the transfer (#2741)."""

import json
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.parsers.bahn import BahnParser
from tests.test_share import share
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


def bahn(name):
    return BahnParser().parse(json.loads((FIX / "bahn.de" / name).read_text(encoding="utf-8")))


def shared_transfers(trip, result, place):  # noqa: F811
    client, auth, trip_id = trip
    post(client, auth, trip_id, offers_of(result))
    page = TestClient(app).get(share(client, trip_id)).text
    legs = page[page.index('<div class="timeline legs">'):]
    return [line.split("</div>")[0] for line in legs.split('<div class="transfer muted">')[1:]
            if place in line.split("</div>")[0]]


def test_koeln_muenchen_shows_platform_4_to_5_at_mannheim_on_the_shared_page(trip):  # noqa: F811
    lines = shared_transfers(trip, bahn("fahrplan-koeln-muenchen.json"), "Mannheim Hbf")
    assert any(" · platform 4 → 5" in line for line in lines)


def test_a_transfer_with_one_platform_shows_no_platform_text_on_the_shared_page(trip):  # noqa: F811
    client, auth, trip_id = trip
    offers = offers_of(bahn("fahrplan-koeln-muenchen.json"))
    for offer in offers:
        for leg in offer["legs"]:
            if leg["from_name"] == "Mannheim Hbf":
                leg["from_platform"] = None
    post(client, auth, trip_id, offers)
    page = TestClient(app).get(share(client, trip_id)).text
    legs = page[page.index('<div class="timeline legs">'):]
    lines = [line.split("</div>")[0] for line in legs.split('<div class="transfer muted">')[1:]
             if "Mannheim Hbf" in line.split("</div>")[0]]
    assert len(lines) == 1
    assert "platform" not in lines[0]
