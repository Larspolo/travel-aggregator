"""One parser class per source (CLAUDE.md, "Code map"). Each parser has `source`, `version` and `parse(raw)`."""

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


def get_parser(source: str):
    from app.parsers.bahn import BahnParser
    from app.parsers.flixbus import FlixbusParser
    from app.parsers.kiwi import KiwiParser
    from app.parsers.ns import NsParser

    parsers = {BahnParser.source: BahnParser, NsParser.source: NsParser, FlixbusParser.source: FlixbusParser,
               KiwiParser.source: KiwiParser}
    return parsers.get(source, lambda: None)()
