"""The change of station between the two trips of a split pair (#1502)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.ranking import Weights, effective_cost
from app.split import split_pairs

T0 = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)
NO_EXTRAS = dict(hour_markup=Decimal("0"), self_transfer_penalty=Decimal("0"))


def _leg(from_name, to_name, start, minutes=60):
    return SimpleNamespace(from_name=from_name, to_name=to_name, from_code=None, to_code=None,
                           depart_at=start, arrive_at=start + timedelta(minutes=minutes))


def row(depart_min, price, w, from_name, to_name, duration_min=60):
    """A ranked row whose itinerary has one leg from `from_name` to `to_name`."""
    dep = T0 + timedelta(minutes=depart_min)
    leg = _leg(from_name, to_name, dep, duration_min)
    it = SimpleNamespace(depart_at=dep, arrive_at=leg.arrive_at, legs=[leg])
    return (it, None, effective_cost(Decimal(price), duration_min, 0, w))


def test_a_change_of_station_pays_the_penalty_and_shows_it():
    w = Weights(station_change_penalty=Decimal("12"), short_transfer_min=10, **NO_EXTRAS)
    a = row(0, "40", w, "Brussels", "Paris Nord")
    b = row(120, "35", w, "Paris Gare de Lyon", "Lyon")
    pairs = split_pairs([a], [b], w)
    assert len(pairs) == 1
    assert pairs[0].total == Decimal("87")
    assert pairs[0].breakdown == "€40 + €35 + €12 change of station = €87"


def test_a_change_of_station_needs_its_own_minimum():
    w = Weights(station_change_min=45, short_transfer_min=10, **NO_EXTRAS)
    a = row(0, "40", w, "Brussels", "Paris Nord")  # arrives at +60
    too_soon = row(90, "35", w, "Paris Gare de Lyon", "Lyon")  # wait 30 minutes
    enough = row(105, "35", w, "Paris Gare de Lyon", "Lyon")  # wait 45 minutes
    pairs = split_pairs([a], [too_soon, enough], w)
    assert [p.second for p in pairs] == [enough]


def test_a_pair_at_one_station_needs_only_the_short_transfer_minimum():
    w = Weights(station_change_min=45, short_transfer_min=10, **NO_EXTRAS)
    a = row(0, "40", w, "Brussels", "Paris Nord")
    same = row(70, "35", w, "Paris Nord", "Lyon")  # wait 10 minutes
    pairs = split_pairs([a], [same], w)
    assert [p.second for p in pairs] == [same]


def test_pairs_at_one_station_do_not_change():
    w = Weights(station_change_penalty=Decimal("12"), short_transfer_min=10, **NO_EXTRAS)
    a = row(0, "40", w, "Brussels", "Paris Nord")
    b = row(120, "35", w, "Paris Nord", "Lyon")
    pairs = split_pairs([a], [b], w)
    assert pairs[0].total == Decimal("75")
    assert pairs[0].breakdown == "€40 + €35 = €75"


def test_a_change_of_station_can_change_the_order():
    w = Weights(station_change_penalty=Decimal("50"), short_transfer_min=10, **NO_EXTRAS)
    a = row(0, "40", w, "Brussels", "Paris Nord")
    other_station = row(120, "45", w, "Paris Gare de Lyon", "Lyon")
    same_station = row(120, "60", w, "Paris Nord", "Lyon")
    pairs = split_pairs([a], [other_station, same_station], w)
    assert [p.second for p in pairs] == [same_station, other_station]
