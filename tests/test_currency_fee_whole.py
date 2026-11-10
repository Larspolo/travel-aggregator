"""The currency fee on each page that ranks a fare: the compare view, the shared link and the best offer of the
ingest response (#1993, epic #1992). A trip profile of 2 % adds 1.90 € to a CHF 100 fare at a rate of 0.95;
a profile of 0 % adds no part."""
import copy
import dataclasses
import re
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import CurrencyRate, Fare, Itinerary, Trip
from app.profiles import save
from app.ranking import Weights
from tests.test_ingest_api import BODY
from tests.test_trip_booked import csrf
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

FEE = Decimal("1.90")  # 2 % of the EUR price 95.00


def _set_profile_fee(sessions, trip_id, pct):
    """The trip uses a profile whose currency fee is `pct` percent."""
    with sessions() as s:
        profile = save(s, "Abroad", dataclasses.replace(Weights(), currency_fee_pct=Decimal(pct)))
        s.get(Trip, trip_id).profile_id = profile.id
        s.commit()


def _set_chf_fare(sessions, trip_id):
    """The fare of the 100 € offer is CHF 100 at a rate of 0.95 (so 95 € and a 2 % fee of 1.90 €)."""
    with sessions() as s:
        for f in s.scalars(select(Fare).join(Itinerary, Fare.itinerary_id == Itinerary.id)
                           .where(Itinerary.trip_id == trip_id, Fare.latest_price == Decimal("100.00"))):
            f.currency = "CHF"
        s.add(CurrencyRate(code="CHF", eur_per_unit=Decimal("0.95"), updated_at=datetime.now(timezone.utc)))
        s.commit()


def _ingest_expensive(client, auth, trip_id):
    """Ingest the 150 € offer, the more expensive one; returns the `best` of the ingest response."""
    body = copy.deepcopy(BODY)
    body.update(trip_id=trip_id, offers=[offer("150.00", "ICE 2")])
    r = client.post("/api/ingest", json=body, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()["best"]


def _breakdown_totals(page):
    """The total (the last amount after "= €") of each breakdown of a page, in page order."""
    texts = re.findall(r'class="breakdown[^"]*">([^<]*)<', page)
    return [Decimal(re.findall(r"= €([\d.]+)", t)[-1]) for t in texts]


def _share_link(client, trip_id):
    r = client.post(f"/trips/{trip_id}/share", data={"csrf_token": csrf(client, trip_id)})
    assert r.status_code == 200
    return re.search(r'<pre class="share-link">([^<]+)</pre>', r.text).group(1).removeprefix("http://testserver")


def _seed(client, auth, trip_id, sessions, pct):
    """A profile of `pct` %, a CHF offer of 100 € and a 150 € offer; returns the ids and the ingest best."""
    _set_profile_fee(sessions, trip_id, pct)
    ingest(client, auth, trip_id, [offer("100.00", "ICE 1")])
    _set_chf_fare(sessions, trip_id)
    best = _ingest_expensive(client, auth, trip_id)
    with sessions() as s:
        ids = [i.id for i in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id).order_by(Itinerary.id))]
    return ids, best


def _pages(client, trip_id, ids):
    """The compare view of both itineraries (the CHF offer first) and the shared link."""
    compare = client.get(f"/trips/{trip_id}/compare", params={"it": ids}).text
    shared = client.get(_share_link(client, trip_id)).text
    return compare, shared


def test_a_2_percent_profile_adds_the_currency_fee_on_each_page(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ids, best = _seed(client, auth, trip_id, sessions, "2")
    compare, shared = _pages(client, trip_id, ids)
    assert "currency fee" in compare and "currency fee" in shared
    compare_total = _breakdown_totals(compare)[0]
    assert _breakdown_totals(shared)[0] == compare_total
    assert best["currency"] == "CHF" and best["price"] == "100.00"
    assert Decimal(best["total"]) == compare_total  # the best is the CHF offer: the same total

    _set_profile_fee(sessions, trip_id, "0")
    compare0, shared0 = _pages(client, trip_id, ids)
    best0 = _ingest_expensive(client, auth, trip_id)
    assert _breakdown_totals(compare0)[0] == compare_total - FEE
    assert _breakdown_totals(shared0)[0] == compare_total - FEE
    assert Decimal(best0["total"]) == Decimal(best["total"]) - FEE


def test_a_0_percent_profile_shows_no_currency_fee(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ids, _ = _seed(client, auth, trip_id, sessions, "0")
    compare, shared = _pages(client, trip_id, ids)
    assert "currency fee" not in compare
    assert "currency fee" not in shared
