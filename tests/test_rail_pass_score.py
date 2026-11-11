"""The cost of a rail pass in place of the fare price (#2267, epic #2263)."""

import copy
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import Itinerary, RailPass, Trip
from app.ranking import Weights, bar_parts, format_breakdown
from app.web.pages import row_cost
from tests.test_trip_page import ingest, offer, trip  # noqa: F401  (trip is a fixture)

STALE = datetime(2000, 1, 1, tzinfo=timezone.utc)
WEIGHTS = Weights(reservation_fee=Decimal("10.00"))


def bus(price):
    o = copy.deepcopy(offer(price, "FLX 1", "Flixbus"))
    o["legs"] = [dict(o["legs"][0], mode="bus", carrier="Flixbus")]
    return o


def chf(price):
    o = copy.deepcopy(offer(price, "IC 8"))
    o["price_currency"] = "CHF"
    return o


def _setup(sessions, trip_id, with_pass):
    with sessions() as s:
        if with_pass:
            rp = RailPass(name="Interrail", first_day=date(2026, 12, 1), last_day=date(2026, 12, 31),
                          day_cost=Decimal("40.00"), carriers="", updated_at=datetime.now(timezone.utc))
            s.add(rp)
            s.flush()
            s.get(Trip, trip_id).rail_pass_id = rp.id
        for it in s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)):
            for f in it.fares:
                if f.latest_price == Decimal("139.90"):
                    f.reservation_legs = 1
        s.commit()


def _costs(sessions, trip_id, rates=None):
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
        out = {}
        for it in its:
            fare, b = row_cost(it, it.fares, [], WEIGHTS, STALE, rates or {})
            out[fare.latest_price] = b
        return out


def _labels(b):
    return dict(((label, value) for label, value in b.extras), price=b.price)


def test_the_pass_replaces_the_price_of_a_covered_train(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("139.90", "ICE 1"), bus("49.00")])
    _setup(sessions, trip_id, with_pass=True)
    costs = _costs(sessions, trip_id)
    ice, flix = costs[Decimal("139.90")], costs[Decimal("49.00")]
    assert ice.price == 0 and ice.extras[0] == ("pass Interrail", Decimal("40.00"))
    assert ("reservation", Decimal("10.00")) in ice.extras
    text = format_breakdown(ice)
    assert "€40 pass Interrail" in text and "€10 reservation" in text and "price" not in text
    assert "price" not in [label for label, _, _ in bar_parts(ice)]
    assert flix.price == Decimal("49.00") and "€49 price" in format_breakdown(flix)


def test_no_pass_keeps_the_old_breakdown(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [offer("139.90", "ICE 1"), bus("49.00")])
    _setup(sessions, trip_id, with_pass=False)
    costs = _costs(sessions, trip_id)
    ice = costs[Decimal("139.90")]
    assert ice.price == Decimal("139.90") and not any(label.startswith("pass") for label, _ in ice.extras)
    assert "€139.90 price" in format_breakdown(ice)
    assert costs[Decimal("49.00")].price == Decimal("49.00")


def test_a_covered_chf_fare_has_no_chf_text_and_no_currency_fee(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, [chf("120.00")])
    _setup(sessions, trip_id, with_pass=True)
    with sessions() as s:
        it = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).one()
        weights = Weights(currency_fee_pct=Decimal("2"))
        _, b = row_cost(it, it.fares, [], weights, STALE, {"CHF": Decimal("1.05")})
    text = format_breakdown(b)
    assert "CHF" not in text and "currency fee" not in text and "€40 pass Interrail" in text
