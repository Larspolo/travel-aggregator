"""The SBB fare names follow the saver mark of sbb.ch (#2820).

sbb.ch marks a saver price with "%". In the TripPrices response such a price has `afterSaleFlexibility`
FULL_FLEXIBLE, and the normal price (Basel SBB → Zürich HB: CHF 36.00 2nd class, CHF 18.00 with the Half Fare card)
has NON_FLEXIBLE.
"""
from decimal import Decimal

from app.parsers.sbb import SbbParser
from tests.test_sbb_parser import FULL, HALF, load


def _names(path):
    return {(o.price_amount, o.travel_class): (o.fare_name, o.flexibility) for o in SbbParser().parse(load(path)).offers}


def test_the_normal_half_fare_price_is_flex():
    assert _names(HALF)[(Decimal("18.00"), "standard")] == ("Flex, 2nd class", "Flex")


def test_a_cheaper_saver_price_is_saver():
    names = _names(FULL)
    assert names[(Decimal("19.40"), "standard")] == ("Saver, 2nd class", "Saver")
