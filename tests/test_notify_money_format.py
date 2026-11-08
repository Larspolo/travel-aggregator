"""A price-drop message shows each amount with 2 decimals (found in the ntfy check of #868 and #525 on the preview,
2026-11-08: "EUR 95.00 → EUR 78.0"). The new price comes from the ingest body (JSON 78.00 gives Decimal("78.0")),
the old price from the database (Numeric(…, 2))."""

from decimal import Decimal

from app.notify import PriceDrop, _line


def drop(old, new):
    return PriceDrop(trip_id=1, fare_name="Sparpreis", source="bahn.de", currency="EUR", old_price=old, new_price=new)


def test_both_amounts_have_two_decimals():
    assert _line(drop(Decimal("95.00"), Decimal("78.0"))) == "Sparpreis (bahn.de): EUR 95.00 → EUR 78.00"


def test_a_new_fare_has_two_decimals():
    assert _line(drop(None, Decimal("40"))) == "Sparpreis (bahn.de): EUR 40.00"


def test_cents_stay_as_they_are():
    assert _line(drop(Decimal("50.5"), Decimal("49.99"))) == "Sparpreis (bahn.de): EUR 50.50 → EUR 49.99"
