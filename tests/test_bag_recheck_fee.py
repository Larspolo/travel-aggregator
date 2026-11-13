"""The bag recheck fee (#2661): "Bag recheck € per transfer" in "Advanced" adds the fee for each leg with
`bag_recheck` true as the part "bag recheck at <from_name>"; nothing on a trip with "Checked bag: none"."""
from decimal import Decimal
from types import SimpleNamespace

from app.models import Trip
from app.ranking import Weights
from app.risk import recheck_extras
from tests.test_bike_fee import _totals
from tests.test_self_transfer import post
from tests.test_trip_page import offer, trip  # noqa: F401  (trip is a fixture)


def _it(*rechecks, bag=None):
    legs = [SimpleNamespace(from_name=f"S{i}", bag_recheck=r) for i, r in enumerate(rechecks)]
    return SimpleNamespace(legs=legs, trip=SimpleNamespace(checked_bag=bag))


def test_the_fee_adds_one_part_per_recheck_leg():
    w = Weights(recheck_fee=Decimal("30"))
    assert recheck_extras(None, _it(None, True, False), w) == (("bag recheck at S1", Decimal("30")),)
    assert recheck_extras(None, _it(False, None), w) == ()


def test_no_checked_bag_or_a_zero_fee_adds_no_part():
    assert recheck_extras(None, _it(True, bag="none"), Weights(recheck_fee=Decimal("30"))) == ()
    assert recheck_extras(None, _it(True), Weights()) == ()


def _recheck_offer(recheck=True):
    o = offer("89.90")
    o["legs"][1]["from_name"] = "OPO"
    if recheck:
        o["legs"][1]["bag_recheck"] = True
    return o


def _set_bag(sessions, trip_id, value):
    with sessions() as s:
        s.get(Trip, trip_id).checked_bag = value
        s.commit()


def test_the_breakdown_and_the_score_with_a_recheck_leg(trip):  # noqa: F811
    client, auth, trip_id = trip
    post(client, auth, trip_id, [_recheck_offer()])
    default = client.get(f"/trips/{trip_id}").text
    assert "bag recheck" not in default
    page = client.get(f"/trips/{trip_id}?recheck_fee=30").text
    assert "€30 bag recheck at OPO" in page
    assert _totals(page)[0] == str(Decimal(_totals(default)[0]) + 30)


def test_no_recheck_leg_or_no_checked_bag_does_not_change(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    post(client, auth, trip_id, [_recheck_offer(recheck=False)])
    assert _totals(client.get(f"/trips/{trip_id}").text) == _totals(client.get(f"/trips/{trip_id}?recheck_fee=30").text)


def test_no_checked_bag_on_the_trip_adds_no_fee(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _set_bag(sessions, trip_id, "none")
    post(client, auth, trip_id, [_recheck_offer()])
    assert _totals(client.get(f"/trips/{trip_id}").text) == _totals(client.get(f"/trips/{trip_id}?recheck_fee=30").text)
