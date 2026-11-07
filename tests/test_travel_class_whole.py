"""The 1st class bonus on a whole bahn.de capture with both classes: the trip page and the compare page (#693, #689)."""

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import select

from app.models import Itinerary
from app.ranking import CENT, Weights
from app.web.pages import row_cost
from tests.test_bahn_whole import FIX, post, trip  # noqa: F401  (trip is a fixture)
from tests.test_compare_select import _submit

# the recon capture has the fares of both classes (reiseAngebote) of one connection; the Zürich fahrplan has 2nd class
# fares only, so it gives the 2nd class rows of the trip (its connections are other itineraries)
CAPTURES = ["recon-169.json", "fahrplan-amsterdam-zuerich.json"]
BREAKDOWN = re.compile(r'class="breakdown">([^<]*)')
ORDER = re.compile(r'class="(?:total|breakdown)">([^<]*)')
STALE = datetime.now(UTC) - timedelta(hours=24)


def _ingest(client, auth, trip_id):
    for name in CAPTURES:
        raw = json.loads((FIX / name).read_text(encoding="utf-8"))
        assert post(client, auth, trip_id, raw)["created"] > 0


def _bonus(duration_min):
    """The amount of the 1st class part for an itinerary, rounded as the score rounds it."""
    return (Decimal("-10") * duration_min / 60).quantize(CENT, rounding=ROUND_HALF_EVEN)


def _label(value):
    """The amount as the breakdown writes it: whole euros without decimals, otherwise two digits."""
    return f"€{int(value)}" if value == value.to_integral_value() else f"€{value:.2f}"


def _chosen(it, weights):
    """The main fare of an itinerary, as the trip page chooses it."""
    return row_cost(it, it.fares, [], weights, STALE)


def _row(page, it_id):
    """The trip-table row of one itinerary: the row that has its compare box."""
    return next(part for part in page.split("<tr") if f'value="{it_id}"' in part and 'class="breakdown"' in part)


def test_each_first_class_fare_gets_the_bonus_of_its_itinerary(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest(client, auth, trip_id)
    weights = Weights(first_class_hour=Decimal("-10"))
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
        classes = {f.travel_class for it in its for f in it.fares}
        assert {"first", "standard"} <= classes
        for it in its:
            for fare in it.fares:
                _, cost = row_cost(it, [fare], [], weights, STALE)
                bonus = [amount for label, amount in cost.extras if label == "1st class"]
                if fare.travel_class == "first":
                    assert bonus == [_bonus(it.duration_min)]
                else:
                    assert bonus == []


def test_the_trip_page_shows_the_line_on_the_rows_with_a_first_class_main_fare(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest(client, auth, trip_id)
    weights = Weights(first_class_hour=Decimal("-10"))
    page = client.get(f"/trips/{trip_id}", params={"first_class_hour": "-10"}).text
    breakdowns = BREAKDOWN.findall(page)
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
        expected = []
        for it in its:
            fare, _cost = _chosen(it, weights)
            if fare.travel_class == "first":
                expected.append(f"{_label(_bonus(it.duration_min))} 1st class")
            else:
                assert "1st class" not in BREAKDOWN.findall(_row(page, it.id))[0]
    assert len([b for b in breakdowns if "1st class" in b]) == len(expected) > 0
    for text in expected:
        assert any(text in b for b in breakdowns), text


def test_an_amount_of_zero_gives_no_line_and_the_same_order(trip):  # noqa: F811
    client, auth, trip_id = trip
    _ingest(client, auth, trip_id)
    plain = client.get(f"/trips/{trip_id}").text
    zero = client.get(f"/trips/{trip_id}", params={"first_class_hour": "0"}).text
    assert not any("1st class" in b for b in BREAKDOWN.findall(zero))
    assert ORDER.findall(zero) == ORDER.findall(plain)
    assert len(ORDER.findall(zero)) > 0


def test_the_compare_page_shows_the_totals_of_the_trip_page(trip, sessions):  # noqa: F811
    client, auth, trip_id = trip
    _ingest(client, auth, trip_id)
    weights = Weights(first_class_hour=Decimal("-10"))
    page = client.get(f"/trips/{trip_id}", params={"first_class_hour": "-10"}).text
    with sessions() as s:
        its = s.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id)).all()
        # with a bonus, a 1st class fare is the main fare of its row; a row with 2nd class fares only has no bonus
        first_id = next(it.id for it in its if _chosen(it, weights)[0].travel_class == "first")
        std_id = next(it.id for it in its if all(f.travel_class == "standard" for f in it.fares))

    response = _submit(client, page, [first_id, std_id])
    assert response.status_code == 200
    columns = BREAKDOWN.findall(response.text)
    assert len(columns) == 2
    assert columns == [BREAKDOWN.findall(_row(page, first_id))[0], BREAKDOWN.findall(_row(page, std_id))[0]]
    assert "1st class" in columns[0] and "1st class" not in columns[1]
