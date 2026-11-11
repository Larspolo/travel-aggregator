"""A split pair uses the minimum of a via place even when it is below the global minimum (#2097)."""


from app.ranking import Weights
from app.split import split_pairs
from tests.test_split_station_change import NO_EXTRAS, row


def _w(**kw):
    return Weights(short_transfer_min=10, transfer_place1_name="Köln Hbf", transfer_place1_min=5,
                   **NO_EXTRAS, **kw)


def test_a_wait_at_or_above_a_lower_place_minimum_gives_the_pair():
    w = _w()
    a = row(0, "40", w, "Brussels", "Köln Hbf")  # arrives at +60
    b = row(67, "35", w, "Köln Hbf", "Berlin")  # wait 7 minutes: below the global 10, above the place's 5
    assert len(split_pairs([a], [b], w)) == 1


def test_a_wait_below_a_lower_place_minimum_gives_no_pair():
    w = _w()
    a = row(0, "40", w, "Brussels", "Köln Hbf")
    b = row(64, "35", w, "Köln Hbf", "Berlin")  # wait 4 minutes: below the place's 5
    assert split_pairs([a], [b], w) == []


def test_a_pair_with_no_place_slot_still_needs_the_global_minimum():
    w = _w()
    a = row(0, "40", w, "Brussels", "Lyon")
    b = row(64, "35", w, "Lyon", "Berlin")  # wait 4 minutes: below the global 10
    assert split_pairs([a], [b], w) == []
