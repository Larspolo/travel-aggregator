"""POST /api/ingest (#54): a bad offer is rejected with its index and a short reason; the other offers are stored."""

import copy

import pytest
from sqlalchemy import func, select

from app.models import Itinerary
from tests.test_ingest_api import BODY, setup  # noqa: F401  (fixture)

GOOD = BODY["offers"][0]


def offer(service_no, **change):
    o = copy.deepcopy(GOOD)
    o["legs"][0]["service_no"] = service_no
    o.update(change)
    return o


def test_one_bad_offer_is_rejected_and_two_good_offers_are_stored(setup, sessions):  # noqa: F811
    client, auth, trip_id = setup
    offers = [offer("ICE 1"), offer("ICE 2", price_currency="<script>"), offer("ICE 3")]
    r = client.post("/api/ingest", json={**copy.deepcopy(BODY), "trip_id": trip_id, "offers": offers}, headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert (data["created"], data["updated"], data["unchanged"], data["rejected"]) == (2, 0, 0, 1)
    assert [e["index"] for e in data["errors"]] == [1]
    assert "price_currency" in data["errors"][0]["reason"] and "<script>" not in r.text
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Itinerary)) == 2


@pytest.mark.parametrize("path, value", [
    (("legs", 0, "depart_at"), "2026-12-20T07:34:00"),
    (("price_amount",), "89.999"),
    (("price_amount",), "a lot"),
    (("legs",), []),
    (("legs", 0, "mode"), "rocket"),
    (("booking_url",), "javascript:alert(1)"),
    (("legs", 1, "depart_at"), "2026-12-20T13:00:00+01:00"),
])
def test_a_single_bad_offer_gets_200_with_rejected(setup, sessions, path, value):  # noqa: F811
    client, auth, trip_id = setup
    o = copy.deepcopy(GOOD)
    target = o
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    r = client.post("/api/ingest", json={**copy.deepcopy(BODY), "trip_id": trip_id, "offers": [o]}, headers=auth)
    assert r.status_code == 200
    assert set(r.json()) == {"created", "updated", "unchanged", "rejected", "errors", "warning", "trip_id", "trip_title", "suggestion"}
    assert r.json()["rejected"] == 1 and r.json()["errors"][0]["index"] == 0
    with sessions() as s:
        assert s.scalar(select(func.count()).select_from(Itinerary)) == 0


def test_the_client_cannot_set_the_errors(setup):  # noqa: F811
    client, auth, trip_id = setup
    b = {**copy.deepcopy(BODY), "trip_id": trip_id, "offer_errors": [{"index": 9, "reason": "x"}]}
    r = client.post("/api/ingest", json=b, headers=auth)
    assert r.status_code == 200 and r.json()["rejected"] == 0 and r.json()["errors"] == []
