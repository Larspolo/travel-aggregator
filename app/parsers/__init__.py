"""One parser class per source (CLAUDE.md, "Code map"). Each parser has `source`, `version` and `parse(raw)`.
A parser whose price is for all travelers of the capture has `group_price = True` (#767; its fixture README)."""

from dataclasses import dataclass, field
from typing import Any

from app.schemas import OfferIn


@dataclass
class ParseResult:
    """The offers of a raw payload, and one entry {"index", "reason"} per rejected connection (fail soft)."""

    offers: list[OfferIn] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    # The number of travelers of the prices (#764); None when the payload does not tell it.
    travelers: int | None = None


def count(value: Any) -> int | None:
    """A traveler count from 1 to 9, else None (P5: the payload is untrusted)."""
    return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 9 else None


def parser_classes() -> dict[str, type]:
    """The parser class of each source, keyed by its `source` name, in a fixed order."""
    from app.parsers.bahn import BahnParser
    from app.parsers.flixbus import FlixbusParser
    from app.parsers.kiwi import KiwiParser
    from app.parsers.ns import NsParser

    return {c.source: c for c in (BahnParser, NsParser, FlixbusParser, KiwiParser)}


def all_sources() -> list[str]:
    """The `source` names of all parsers, in a fixed order (#967)."""
    return list(parser_classes())


def get_parser(source: str):
    return parser_classes().get(source, lambda: None)()


def group_price(source: str) -> bool:
    """True when the price of the source is for all travelers of the capture (#767), not per traveler."""
    return bool(getattr(get_parser(source), "group_price", False))
