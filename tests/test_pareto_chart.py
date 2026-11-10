"""The chart of the price against the door-to-door hours on the trip page (#1858)."""

from decimal import Decimal

from app.pareto import pareto_ids
from app.pareto_chart import pareto_chart
from tests.test_history_whole import capture, trip  # noqa: F401  (trip is a fixture)

POINTS = [(1, "train", Decimal("40.00"), 300), (2, "flight", Decimal("90.00"), 180),
          (3, "bus", Decimal("60.00"), 400)]


def test_three_offers_give_three_points_and_two_filled():
    marked = pareto_ids([(i, p, m) for i, _, p, m in POINTS])
    chart = pareto_chart(POINTS, marked)
    assert len(chart["dots"]) == 3
    assert {d["id"] for d in chart["dots"] if d["marked"]} == {1, 2}
    assert chart["line"].count(",") == 2  # the line joins the 2 marked points
    assert chart["dots"][0]["title"] == "train: €40.00, 5h00 door to door"


def test_the_points_stay_inside_the_view_box():
    chart = pareto_chart(POINTS, set())
    for d in chart["dots"]:
        assert 0 < d["x"] < chart["width"] and 0 < d["y"] < chart["height"]


def test_one_offer_gives_no_chart():
    assert pareto_chart(POINTS[:1], {1}) is None


def test_the_trip_page_with_one_offer_has_no_chart(trip):  # noqa: F811
    client, auth, trip_id = trip
    capture(client, auth, trip_id, "90.00", "2026-11-03T10:00:00Z")
    assert "Price and door-to-door hours" not in client.get(f"/trips/{trip_id}").text
