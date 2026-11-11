"""The routes of the shown rows of a trip (trip:routes, #2224)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models import Fare, Itinerary, Leg
from app.ranking import Weights
from app.trip_routes import trip_routes
from app.web.pages import row_cost

_NO_STALE = datetime.min.replace(tzinfo=UTC)
_WEIGHTS = Weights(hour_markup=Decimal("0"), transfer_markup=Decimal("0"))  # no markup: the effective cost is the price
_DEP = datetime(2026, 12, 20, 6, 0, tzinfo=UTC)


def _row(n, price, *, via=(), mode="train", currency="EUR"):
    """A row of `trip_page()`: a train from Berlin to Paris, with one leg per transfer place in `via`."""
    stops = ["Berlin", *via, "Paris"]
    it = Itinerary(fingerprint=f"fp{n}", depart_at=_DEP, arrive_at=_DEP + timedelta(hours=2 * len(stops) - 2),
                   duration_min=60, transfers=len(via), mode_summary=mode)
    it.legs = []
    for seq, (start, end) in enumerate(zip(stops, stops[1:])):
        it.legs.append(Leg(seq=seq, mode=mode, carrier="X", from_name=start, to_name=end, depart_at=_DEP,
                           depart_offset_min=0, arrive_at=_DEP, arrive_offset_min=0))
    fare = Fare(source="src", latest_price=Decimal(price), currency=currency, latest_captured_at=_DEP)
    fare.itinerary = it
    _, cost = row_cost(it, [fare], [], _WEIGHTS, _NO_STALE)
    return it, fare, cost


def _summary(routes):
    return [(r.label, r.count, r.diff, r.best[0].fingerprint, r.cheapest) for r in routes]


def test_routes_are_ordered_by_the_best_row_with_the_difference_to_the_trip_best():
    rows = [
        _row(1, "120.00"), _row(2, "130.00"), _row(3, "150.00"),
        _row(4, "104.00", via=["Brussels"]), _row(5, "110.00", via=["brussels"]),
    ]
    routes = trip_routes(rows)
    assert _summary(routes) == [
        ("via Brussels", 2, Decimal("0.00"), "fp4", Decimal("104.00")),
        ("Direct", 3, Decimal("16.00"), "fp1", Decimal("120.00")),
    ]


def test_the_label_uses_the_spelling_of_the_first_row():
    rows = [_row(1, "110.00", via=["brussels"]), _row(2, "104.00", via=["Brussels"])]
    routes = trip_routes(rows)
    assert [r.label for r in routes] == ["via brussels"]
    assert routes[0].key == ("brussels",)


def test_two_transfer_places_are_joined_in_leg_order():
    routes = trip_routes([_row(1, "50.00", via=["Liège", "Brussels"])])
    assert [r.label for r in routes] == ["via Liège, Brussels"]


def test_no_rows_give_an_empty_list():
    assert trip_routes([]) == []


def test_a_row_with_no_rate_does_not_count():
    no_rate = _row(1, "5.00", via=["Brussels"], currency="CHF")
    rated = _row(2, "50.00")
    routes = trip_routes([no_rate, rated])
    assert _summary(routes) == [("Direct", 1, Decimal("0.00"), "fp2", Decimal("50.00"))]
