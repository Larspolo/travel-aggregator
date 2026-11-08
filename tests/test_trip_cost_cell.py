"""The cost cell shows the effective cost, a breakdown bar and the text; badges have a class of their kind (#590)."""

import re
from decimal import Decimal

from app.ranking import Breakdown, bar_parts, format_total
from tests.test_trip_hide import trip  # noqa: F401


def test_the_bar_parts_are_percent_of_the_positive_parts():
    b = Breakdown(price=Decimal(90), time_cost=Decimal(60), transfer_cost=Decimal(0), total=Decimal(150))
    assert bar_parts(b) == [("price", Decimal(0), Decimal("60.0")), ("time", Decimal("60.0"), Decimal("40.0"))]
    assert format_total(b) == "€150"
    assert bar_parts(Breakdown(Decimal(0), Decimal(0), Decimal(0), Decimal(0), no_rate="CHF")) == []


def test_a_trip_with_two_offers_has_cost_bars_and_badge_classes(trip):  # noqa: F811
    client, trip_id = trip
    html = client.get(f"/trips/{trip_id}").text
    cells = re.findall(r'<td class="cost">(.*?)</td>', html, flags=re.S)
    assert len(cells) == 2
    for cell in cells:
        assert re.search(r'<div class="total">€[\d.]+</div>', cell)
        assert '<svg class="bar"' in cell and '<rect class="part-0" x="0%"' in cell
        assert '<div class="breakdown">€' in cell and " price" in cell
    for kind in ["best value", "cheapest", "fastest"]:
        assert f'class="badge {kind.replace(" ", "-")}">{kind}</span>' in html
    assert "style=" not in "".join(cells)
