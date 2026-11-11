"""The row shows the place and the minimum of a short transfer at a transfer place (#2074)."""

from decimal import Decimal

from app.ranking import Weights
from app.risk import short_place_marks, transfer_extras
from tests.test_trip_booked import trip  # noqa: F401 (fixture)
from tests.test_transfer_place_minimum import _via

BASE = {"short_transfer_penalty": Decimal("10"), "short_transfer_min": 10}


def test_a_short_transfer_at_the_place_gives_its_line():
    w = Weights(**BASE, transfer_place1_name="Paris CDG", transfer_place1_min=60)
    assert short_place_marks(_via("Paris CDG"), w) == {0: "short transfer at Paris CDG: 45 min, minimum 60 min"}


def test_no_minimum_a_long_transfer_or_another_place_gives_no_line():
    assert short_place_marks(_via("Paris CDG"), Weights(**BASE, transfer_place1_name="Paris CDG")) == {}
    w = Weights(**BASE, transfer_place1_name="Paris CDG", transfer_place1_min=60)
    assert short_place_marks(_via("Paris CDG", gap_min=60), w) == {}
    assert short_place_marks(_via("Köln Hbf"), w) == {}


def test_the_line_and_the_penalty_use_one_rule():
    w = Weights(**BASE, transfer_place1_name="Paris CDG", transfer_place1_min=60)
    assert transfer_extras(_via("Paris CDG"), w) == (("short transfer", Decimal("10")),)
    w = Weights(short_transfer_min=10, short_transfer_penalty=Decimal("0"), transfer_place1_name="Paris CDG", transfer_place1_min=60)
    assert short_place_marks(_via("Paris CDG"), w)  # the line does not need a penalty


def test_the_trip_page_shows_the_line(trip):  # noqa: F811
    client, trip_id = trip
    page = client.get(f"/trips/{trip_id}?transfer_place1_name=Basel&transfer_place1_min=45").text
    assert "short transfer at Basel: 31 min, minimum 45 min" in page
    assert "short transfer at" not in client.get(f"/trips/{trip_id}").text
