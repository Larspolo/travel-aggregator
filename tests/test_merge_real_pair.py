"""The real bahn.de and NS International captures of one search (#482: Amsterdam Centraal → Berlin Hbf, Tue 8 Dec
2026 from 06:00) give one row per shared journey with a fare of each source (#485, the merge of #481)."""

import json
from pathlib import Path

from app.models import Itinerary
from app.parsers.ns import NsParser
from tests.test_bahn_whole import post as post_bahn
from tests.test_ns_whole import post as post_ns
from tests.test_ns_whole import trip  # noqa: F401  (a fixture)

FIX = Path(__file__).parent / "fixtures"
BAHN = FIX / "bahn.de" / "fahrplan-amsterdam-berlin.json"
NS = FIX / "nsinternational.com" / "search-amsterdam-berlin-pair.json"
SHARED = 4  # the NS journeys with offers; each is also in the bahn.de capture (the 07:05 journey has no NS offer)


def _raw(path):
    return json.loads(path.read_text(encoding="utf-8"))



def test_each_shared_journey_is_one_row_with_both_sources(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    post_bahn(client, auth, trip_id, _raw(BAHN))
    post_ns(client, auth, trip_id, _raw(NS))
    ns_journeys = {tuple((leg.service_no, leg.depart_at) for leg in o.legs if leg.mode == "train")
                   for o in NsParser().parse(_raw(NS)).offers}
    with sessions() as s:
        rows = s.query(Itinerary).filter_by(trip_id=trip_id).all()
        by_sources = {it.id: {f.source for f in it.fares} for it in rows}
        both = [it for it in rows if by_sources[it.id] == {"bahn.de", "nsinternational.com"}]
        only_ns = [it for it in rows if by_sources[it.id] == {"nsinternational.com"}]
    assert len(ns_journeys) == SHARED
    assert len(both) == SHARED, f"rows {[(it.id, sorted(by_sources[it.id])) for it in rows]}"
    assert only_ns == []
    page = client.get(f"/trips/{trip_id}").text
    assert page.count("nsinternational.com") >= SHARED and "bahn.de" in page
