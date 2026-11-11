"""The later-transfer markup (#2302): each transfer after the first one costs (value − transfer_markup)."""

from decimal import Decimal
from types import SimpleNamespace

from app.profiles import from_config, to_config
from app.ranking import Weights
from app.risk import later_transfer_extras


def _it(transfers):
    return SimpleNamespace(transfers=transfers, legs=[])


def test_three_transfers_at_transfer_markup_ten_and_later_markup_twenty_five_add_thirty():
    w = Weights(transfer_markup=Decimal("10"), later_transfer_markup=Decimal("25"))
    assert later_transfer_extras(_it(3), w) == (("later transfers", Decimal("30.00")),)


def test_one_transfer_adds_no_part():
    w = Weights(transfer_markup=Decimal("10"), later_transfer_markup=Decimal("25"))
    assert later_transfer_extras(_it(1), w) == ()


def test_no_value_adds_no_part():
    assert later_transfer_extras(_it(3), Weights(transfer_markup=Decimal("10"))) == ()


def test_a_value_equal_to_the_transfer_markup_adds_no_part():
    w = Weights(transfer_markup=Decimal("10"), later_transfer_markup=Decimal("10"))
    assert later_transfer_extras(_it(3), w) == ()


def test_a_lower_value_gives_a_discount():
    w = Weights(transfer_markup=Decimal("10"), later_transfer_markup=Decimal("4"))
    assert later_transfer_extras(_it(3), w) == (("later transfers", Decimal("-12.00")),)


def test_the_value_survives_a_profile_config():
    w = Weights(later_transfer_markup=Decimal("25"))
    assert from_config(to_config(w)) == w
    assert from_config(to_config(Weights())).later_transfer_markup is None
