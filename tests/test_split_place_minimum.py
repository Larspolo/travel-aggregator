"""The minimum of the via place for split pairs (#2075)."""


from app.ranking import Weights
from app.split import split_pairs
from tests.test_split_station_change import NO_EXTRAS, row


def _w(**kw):
    return Weights(short_transfer_min=10, transfer_place1_name="Paris CDG", transfer_place1_min=60,
                   **NO_EXTRAS, **kw)


def test_a_wait_below_the_place_minimum_gives_no_pair():
    w = _w()
    a = row(0, "40", w, "Brussels", "Paris CDG")  # arrives at +60
    b = row(105, "35", w, "Paris CDG", "Rome")  # wait 45 minutes
    assert split_pairs([a], [b], w) == []


def test_a_wait_above_the_place_minimum_gives_the_pair():
    w = _w()
    a = row(0, "40", w, "Brussels", "Paris CDG")
    b = row(130, "35", w, "Paris CDG", "Rome")  # wait 70 minutes
    assert len(split_pairs([a], [b], w)) == 1


def test_a_via_place_with_no_slot_pairs_as_before():
    w = _w()
    a = row(0, "40", w, "Brussels", "Lyon")
    b = row(80, "35", w, "Lyon", "Rome")  # wait 20 minutes
    assert len(split_pairs([a], [b], w)) == 1


def test_a_change_of_station_with_a_larger_minimum_wins():
    w = _w(station_change_min=90)
    a = row(0, "40", w, "Brussels", "Paris CDG")
    b = row(130, "35", w, "Paris Orly", "Rome")  # wait 70 minutes, change needs 90
    assert split_pairs([a], [b], w) == []
