"""The carrier loyalty (#2432): "Carrier N loyalty %" in "Advanced" subtracts that percent of the EUR price per
traveler from a fare whose legs are all of the carrier of the slot (`loyalty_extras`)."""

import re
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select

from app.models import ScoreProfile
from app.profiles import from_config
from app.ranking import Weights, effective_cost
from app.risk import loyalty_extras
from tests.test_trip_booked import csrf
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

DB = Weights(carrier1_name="Deutsche Bahn", carrier1_loyalty_pct=Decimal("5"))


def _it(*carriers):
    return SimpleNamespace(legs=[SimpleNamespace(carrier=c) for c in carriers])


def test_a_fare_of_only_that_carrier_gets_minus_the_percent():
    extras = loyalty_extras(_it("Deutsche Bahn", "deutsche bahn "), Decimal("80.00"), DB)
    assert extras == (("loyalty Deutsche Bahn", Decimal("-4.0000")),)
    assert effective_cost(Decimal("80"), 0, 0, DB, extras).total == effective_cost(Decimal("80"), 0, 0, DB, ()).total - 4


def test_an_other_carrier_a_mixed_itinerary_and_no_rate_give_no_part():
    assert loyalty_extras(_it("FlixBus"), Decimal("80"), DB) == ()
    assert loyalty_extras(_it("Deutsche Bahn", "ÖBB"), Decimal("80"), DB) == ()
    assert loyalty_extras(_it("Deutsche Bahn"), None, DB) == ()
    assert loyalty_extras(_it("Deutsche Bahn"), Decimal("80"), Weights(carrier1_name="Deutsche Bahn")) == ()


def test_a_markup_of_zero_and_loyalty_give_only_the_loyalty_part():
    from app.risk import carrier_extras
    assert carrier_extras(_it("Deutsche Bahn"), DB) == ()
    assert loyalty_extras(_it("Deutsche Bahn"), Decimal("80"), DB) != ()


def test_the_trip_page_shows_the_part_and_the_url_wins(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    o = offer("80.00", "ICE 1", carrier="Deutsche Bahn")
    for leg in o["legs"]:
        leg["carrier"] = "Deutsche Bahn"
    ingest(client, auth, trip_id, [o])
    page = client.get(f"/trips/{trip_id}?carrier1_name=Deutsche%20Bahn&carrier1_loyalty_pct=5").text
    with_loyalty = re.findall(r'class="breakdown[^"]*">([^<]*)<', page)[0]
    assert "€-4 loyalty Deutsche Bahn" in with_loyalty
    assert 'name="carrier1_loyalty_pct" min="0" max="50" step="0.1" value="5"' in page
    page0 = client.get(f"/trips/{trip_id}?carrier1_name=Deutsche%20Bahn").text
    without = re.findall(r'class="breakdown[^"]*">([^<]*)<', page0)[0]
    assert "loyalty" not in without
    total = lambda t: Decimal(re.findall(r"= €([\d.]+)", t)[-1])  # noqa: E731
    assert total(with_loyalty) == total(without) - 4
    for bad in ("51", "-1"):
        assert client.get(f"/trips/{trip_id}?carrier1_loyalty_pct={bad}").status_code == 422


def test_the_profile_form_stores_the_values(trip, sessions):  # noqa: F811
    client, _, trip_id = trip
    base = {"csrf_token": csrf(client, trip_id), "trip_id": trip_id}
    for bad in ("51", "-1"):
        assert client.post("/profiles", data={**base, "name": "Bad", "carrier2_loyalty_pct": bad}).status_code == 422
    data = {**base, "name": "DB", "carrier1_loyalty_pct": "5", "carrier2_loyalty_pct": "2.5",
            "carrier3_loyalty_pct": "10"}
    assert client.post("/profiles", data=data, follow_redirects=False).status_code == 303
    with sessions() as s:
        w = from_config(s.scalars(select(ScoreProfile)).one().config_json)
    assert (w.carrier1_loyalty_pct, w.carrier2_loyalty_pct, w.carrier3_loyalty_pct) == (
        Decimal("5"), Decimal("2.5"), Decimal("10"))
