"""The one money format of the pages and the history (#627, #661): no web import, so the history can use it."""

from decimal import Decimal

CURRENCY_SYMBOLS = {"EUR": "€", "GBP": "£", "USD": "$"}


def money(amount: Decimal, currency: str = "EUR") -> str:
    """One money format for the trip rows (DESIGN.md section 3, #627): the symbol and two decimals, e.g. '€80.90'.

    A currency with no symbol keeps its code: 'CHF 120.00'.
    """
    symbol = CURRENCY_SYMBOLS.get(currency)
    return f"{symbol}{amount:.2f}" if symbol else f"{currency} {amount:.2f}"
