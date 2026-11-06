"""The trip page ranks its rows by effective cost and shows the breakdown of each row (#13)."""

import copy
from datetime import UTC, datetime

from app.models import Itinerary
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)


def direct(price):
    """One leg, 4 hours, no transfer."""
    o = copy.deepcopy(offer(price, "ICE 9"))
    o["legs"] = [dict(o["legs"][0], to_name="Zürich HB", depart_at="2026-12-20T09:00:00+01:00",
                      arrive_at="2026-12-20T13:00:00+01:00")]
    return o


def test_rows_sort_by_effective_cost_and_show_the_breakdown(trip):  # noqa: F811
    client, auth, trip_id = trip
    # 89.90 + 472 min × 15/60 = 118 + 1 transfer × 10 = 217.90; the direct one: 150 + 60 = 210
    ingest(client, auth, trip_id, [offer("89.90"), direct("150.00")])
    page = client.get(f"/trips/{trip_id}").text
    assert "€150 price + €60 time = €210" in page
    assert "€89.90 price + €118 time + €10 transfers = €217.90" in page
    assert page.index("= €210") < page.index("= €217.90")


def test_the_cheapest_fare_is_the_main_row(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("119.90", fare="Flexpreis"), offer("89.90", fare="Sparpreis")])
    page = client.get(f"/trips/{trip_id}").text
    assert "= €217.90" in page and "Flexpreis" not in page


def test_an_itinerary_with_no_fare_does_not_break_the_page(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("89.90")])
    t = datetime(2026, 12, 20, 8, tzinfo=UTC)
    with sessions() as s:
        s.add(Itinerary(trip_id=trip_id, fingerprint="nofare", depart_at=t, arrive_at=t, duration_min=0))
        s.commit()
    r = client.get(f"/trips/{trip_id}")
    assert r.status_code == 200 and "= €217.90" in r.text
