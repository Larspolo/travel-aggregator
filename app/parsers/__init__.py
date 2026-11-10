"""One parser class per source (CLAUDE.md, "Code map"). Each parser has `source`, `version` and `parse(raw)`.
A parser whose price is for all travelers of the capture has `group_price = True` (#767; its fixture README)."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.schemas import OfferIn


@dataclass
class ParseResult:
    """The offers of a raw payload, and one entry {"index", "reason"} per rejected connection (fail soft)."""

    offers: list[OfferIn] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    # The number of travelers of the prices (#764); None when the payload does not tell it.
    travelers: int | None = None
    # The discount cards of the travelers (#1750): [] = no card; None when the payload does not tell it.
    discounts: list[str] | None = None
    # The cheapest price of each day of a day price response (#1196); a day price is not an offer.
    day_prices: list["DayPrice"] = field(default_factory=list)


@dataclass
class DayPrice:
    """The cheapest price of one local day."""

    day: date
    price_amount: Decimal
    price_currency: str


def card_names(values: Any) -> list[str]:
    """The discount card names of a list: its non-empty strings, no duplicates; [] for a value that is no list (P5)."""
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for v in values:
        name = v.strip() if isinstance(v, str) else ""
        if name and name not in out:
            out.append(name)
    return out


def count(value: Any) -> int | None:
    """A traveler count from 1 to 9, else None (P5: the payload is untrusted)."""
    return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 9 else None


def parser_classes() -> dict[str, type]:
    """The parser class of each source, keyed by its `source` name, in a fixed order."""
    from app.parsers.bahn import BahnParser
    from app.parsers.eurostar import EurostarParser
    from app.parsers.flixbus import FlixbusParser
    from app.parsers.kiwi import KiwiParser
    from app.parsers.ns import NsParser
    from app.parsers.oebb import OebbParser
    from app.parsers.sncf import SncfParser
    from app.parsers.trainline import TrainlineParser

    return {c.source: c for c in (BahnParser, NsParser, FlixbusParser, KiwiParser, TrainlineParser, SncfParser, EurostarParser,
                                    OebbParser)}


def all_sources() -> list[str]:
    """The `source` names of all parsers, in a fixed order (#967)."""
    return list(parser_classes())


def get_parser(source: str):
    return parser_classes().get(source, lambda: None)()


def group_price(source: str) -> bool:
    """True when the price of the source is for all travelers of the capture (#767), not per traveler. A manual offer
    gives its count in the form (#1028); a count of 1 keeps the price."""
    if source == "manual":
        return True
    return bool(getattr(get_parser(source), "group_price", False))
