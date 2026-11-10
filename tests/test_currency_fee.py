"""The currency fee in the effective cost (#1993): "Currency fee %" in "Advanced" adds the percent of the EUR price
per traveler for a fare that is not in EUR (`currency_fee_extras`)."""
from decimal import Decimal
from types import SimpleNamespace

from app.currency import to_eur
from app.ranking import Weights
from app.web.pages import currency_fee_extras


def test_a_chf_fare_gets_the_percent_of_its_eur_price():
    rates = {"CHF": Decimal("0.95")}
    eur = to_eur(Decimal("100"), "CHF", rates)
    fare = SimpleNamespace(currency="CHF")
    assert currency_fee_extras(fare, eur, Weights(currency_fee_pct=Decimal("2"))) == (
        ("currency fee", Decimal("1.90")),)


def test_a_eur_fare_a_fare_with_no_rate_and_a_percent_of_zero_get_no_part():
    chf = SimpleNamespace(currency="CHF")
    eur_fare = SimpleNamespace(currency="EUR")
    fee = Weights(currency_fee_pct=Decimal("2"))
    assert currency_fee_extras(eur_fare, Decimal("100"), fee) == ()
    assert currency_fee_extras(chf, None, fee) == ()
    assert currency_fee_extras(chf, Decimal("95"), Weights()) == ()
    assert to_eur(Decimal("100"), "XYZ", {}) is None
