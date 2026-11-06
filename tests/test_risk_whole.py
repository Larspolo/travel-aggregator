"""The risk extras together on the trip page (epic #172, #177): each extra shows in the breakdown, and the extras change
the order of the rows."""

import copy

from tests.test_trip_page import ingest, trip  # noqa: F401  (trip is a fixture)
from tests.test_trip_ranking_page import direct


def _offer(price, legs, flexibility=None):
    o = copy.deepcopy(direct("0"))
    o.update(price_amount=price, flexibility=flexibility, fare_name=None)
    o["legs"] = legs
    return o


def _leg(mode, carrier, service_no, from_name, to_name, depart, arrive, ticket=None):
    leg = {"mode": mode, "carrier": carrier, "service_no": service_no, "from_name": from_name, "to_name": to_name,
           "depart_at": depart, "arrive_at": arrive}
    if ticket is not None:
        leg["ticket"] = ticket
    return leg


def _self_transfer_train(price):
    """Amsterdam 09:00 → Utrecht 10:00, a 5-minute transfer, Utrecht 10:05 → Zürich 13:00 on a second ticket."""
    return _offer(price, [
        _leg("train", "NS", "IC 1", "Amsterdam Centraal", "Utrecht Centraal",
             "2026-12-20T09:00:00+01:00", "2026-12-20T10:00:00+01:00", ticket=1),
        _leg("train", "SBB", "IC 2", "Utrecht Centraal", "Zürich HB",
             "2026-12-20T10:05:00+01:00", "2026-12-20T13:00:00+01:00", ticket=2),
    ])


def _bus(price):
    """Amsterdam 09:00 → Zürich 13:00 by bus, direct."""
    return _offer(price, [
        _leg("bus", "FlixBus", "FLX 12", "Amsterdam Centraal", "Zürich HB",
             "2026-12-20T09:00:00+01:00", "2026-12-20T13:00:00+01:00"),
    ], flexibility="non_refundable")


def _flexible_train(price):
    """Amsterdam 09:00 → Zürich 13:00 by train, direct, with a flexible fare."""
    o = direct(price)
    o["flexibility"] = "flexible"
    return o


BASE = "hour_markup=0&transfer_markup=0"
RISK = ("short_transfer_penalty=20&self_transfer_penalty=30&bus_markup=25"
        "&flex_non_refundable=20&flex_flexible=-20")


def _offers():
    # all risk amounts at 0: the prices alone decide (90 < 100 < 150)
    return [_self_transfer_train("90.00"), _bus("100.00"), _flexible_train("150.00")]


def test_with_all_risk_amounts_at_zero_the_order_is_by_price_and_time(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, _offers())
    page = client.get(f"/trips/{trip_id}?{BASE}&short_transfer_min=10").text
    assert "€90 price = €90" in page and "€100 price = €100" in page and "€150 price = €150" in page
    assert page.index("= €90") < page.index("= €100") < page.index("= €150")


def test_with_the_risk_settings_the_order_changes_and_each_row_shows_its_parts(trip):  # noqa: F811
    client, auth, trip_id = trip
    ingest(client, auth, trip_id, _offers())
    page = client.get(f"/trips/{trip_id}?{BASE}&short_transfer_min=10&{RISK}").text
    # self-transfer train: 90 + 20 short transfer + 30 self-transfer = 140
    # bus: 100 + 25 bus markup + 20 non-refundable = 145
    # direct train: 150 - 20 flexible = 130
    assert "€90 price + €20 short transfer + €30 self-transfer = €140" in page
    assert "€100 price + €25 bus markup + €20 non-refundable = €145" in page
    assert "flexible = €130" in page
    assert page.index("= €130") < page.index("= €140") < page.index("= €145")
