"""The carrier loyalty on each page that ranks a fare: the trip page, the compare view, the trips list and the
shared link (#2433, epic #2432). A loyalty of 5 % for Deutsche Bahn takes 4.00 € from an ICE fare of 80.00 €; a
loyalty of 0 % takes nothing."""
import copy
import dataclasses
import re
from decimal import Decimal

from sqlalchemy import select

from app.models import Itinerary, Trip
from app.profiles import save
from app.ranking import Weights
from tests.test_ingest_api import BODY
from tests.test_trip_booked import csrf
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

LOYALTY = Decimal("4.00")  # 5 % of the 80.00 € fare


def _db_offer(price, service_no):
    """An offer whose legs are all Deutsche Bahn (the loyalty needs every leg of the carrier)."""
    o = offer(price, service_no)
    for leg in o["legs"]:
        leg["carrier"] = "Deutsche Bahn"
    return o


def _set_profile_loyalty(sessions, trip_id, pct):
    """The trip uses a profile whose Deutsche Bahn loyalty is `pct` percent."""
    with sessions() as s:
        profile = save(s, "Rail", dataclasses.replace(Weights(), carrier1_name="Deutsche Bahn",
                                                      carrier1_loyalty_pct=Decimal(pct)))
        s.get(Trip, trip_id).profile_id = profile.id
        s.commit()


def _breakdown_totals(page):
    """The total (the last amount after "= €") of each breakdown of a page, in page order."""
    texts = re.findall(r'class="breakdown[^"]*">([^<]*)<', page)
    return [Decimal(re.findall(r"= €([\d.]+)", t)[-1]) for t in texts]


def _share_link(client, trip_id):
    r = client.post(f"/trips/{trip_id}/share", data={"csrf_token": csrf(client, trip_id)})
    assert r.status_code == 200
    return re.search(r'<pre class="share-link">([^<]+)</pre>', r.text).group(1).removeprefix("http://testserver")


def _seed(client, auth, trip_id, sessions, pct):
    """A profile of `pct` % loyalty, an ICE fare of 80.00 € and one of 150.00 €; returns the itinerary ids and the
    `best` of the ingest response of the 150.00 € offer."""
    _set_profile_loyalty(sessions, trip_id, pct)
    ingest(client, auth, trip_id, [_db_offer("80.00", "ICE 1")])
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, offers=[_db_offer("150.00", "ICE 2")])
    best = client.post("/api/ingest", json=body, headers=auth).json()["best"]
    with sessions() as s:
        ids = [i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id).order_by(Itinerary.id))]
    return ids, best


def _totals(client, trip_id, ids):
    """The first total of the trip page, the compare view and the shared link, and the trips list page."""
    trip_page = client.get(f"/trips/{trip_id}").text
    compare = client.get(f"/trips/{trip_id}/compare", params={"it": ids}).text
    shared = client.get(_share_link(client, trip_id)).text
    return (_breakdown_totals(trip_page)[0], _breakdown_totals(compare)[0], _breakdown_totals(shared)[0],
            client.get("/").text)


def test_a_5_percent_loyalty_lowers_the_effective_cost_on_each_page(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ids, best = _seed(client, auth, trip_id, sessions, "5")
    with_loyalty = _totals(client, trip_id, ids)
    assert "loyalty Deutsche Bahn" in client.get(f"/trips/{trip_id}").text
    assert with_loyalty[0] == with_loyalty[1] == with_loyalty[2]
    assert Decimal(best["total"]) == with_loyalty[1]  # the best is the ICE fare of 80.00 €

    _set_profile_loyalty(sessions, trip_id, "0")
    without = _totals(client, trip_id, ids)
    assert without[0] == with_loyalty[0] + LOYALTY
    assert without[1] == with_loyalty[1] + LOYALTY
    assert without[2] == with_loyalty[2] + LOYALTY
    assert "loyalty Deutsche Bahn" not in client.get(f"/trips/{trip_id}").text
    # The trips list ranks by the raw fare price (`best_price` of app/trips.py), not by the effective cost: the loyalty
    # does not change its "Best" line. A follow-up decides whether the list shows the effective cost.
    assert with_loyalty[3] == without[3]
    assert "Best" in with_loyalty[3] and "€80.00" in with_loyalty[3]
