"""Each trip scores with its own access and egress places (#2109)."""

from datetime import datetime, timezone
from decimal import Decimal

from app.models import AccessTime, Itinerary, Trip, TripAccessTime
from app.ranking import Weights
from app.share import new_link
from app.web.pages import _chosen_offer, best_for_weights
from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _trips(sessions, trip_id):
    """Trip A (the fixture) with an egress of 10 min, trip B with 25 min, trip C with only the global 40 min."""
    with sessions() as s:
        b = Trip(title="B", origin_text="Amsterdam", destination_text="Zürich")
        c = Trip(title="C", origin_text="Amsterdam", destination_text="Zürich")
        s.add_all([b, c, AccessTime(place_text="Zürich HB", kind="egress", minutes=40, cost=Decimal("0"))])
        s.flush()
        s.add_all([TripAccessTime(trip_id=trip_id, place_text="Zürich HB", kind="egress", minutes=10, cost=Decimal("0")),
                   TripAccessTime(trip_id=b.id, place_text="zürich hb", kind="egress", minutes=25, cost=Decimal("0"))])
        s.commit()
        return b.id, c.id


def test_each_trip_uses_its_own_egress(sessions, trip):  # noqa: F811
    client, auth, a_id = trip
    b_id, c_id = _trips(sessions, a_id)
    for t in (a_id, b_id, c_id):
        ingest(client, auth, t, [direct("150.00")])
    page_a = client.get(f"/trips/{a_id}?hour_markup=30").text
    page_b = client.get(f"/trips/{b_id}?hour_markup=30").text
    page_c = client.get(f"/trips/{c_id}?hour_markup=30").text
    assert "€5 egress time (this trip)" in page_a
    assert "€12.50 egress time (this trip)" in page_b
    assert "€20 egress time" in page_c and "(this trip)" not in page_c


def test_best_offer_compare_and_share_match_the_table(sessions, trip):  # noqa: F811
    client, auth, a_id = trip
    _trips(sessions, a_id)
    ingest(client, auth, a_id, [direct("150.00"), direct("160.00") | {"legs": [
        dict(direct("160.00")["legs"][0], service_no="ICE 11", depart_at="2026-12-20T10:00:00+01:00",
             arrive_at="2026-12-20T14:00:00+01:00")]}])
    # 150 + 60 time + 2.50 egress (10 min at the default €15) = 212.50
    assert "€2.50 egress time (this trip) = €212.50" in client.get(f"/trips/{a_id}").text
    now = datetime.now(timezone.utc)
    with sessions() as s:
        t = s.get(Trip, a_id)
        w = Weights()
        assert best_for_weights(s, t, w, now)[2].total == Decimal("212.50")
        assert _chosen_offer(s, t, w, [], now)[2].total == Decimal("212.50")
        ids = [i.id for i in s.query(Itinerary).filter_by(trip_id=a_id)]
        token = new_link(t)
        s.commit()
    compare = client.get(f"/trips/{a_id}/compare", params={"it": ids}).text
    assert "€212.50" in compare and "egress time (this trip)" in compare
    shared = client.get(f"/s/{token}").text
    assert "€212.50" in shared and "egress time (this trip)" in shared
