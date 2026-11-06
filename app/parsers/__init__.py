"""One parser class per source (CLAUDE.md, "Code map"). Each parser has `source`, `version` and `parse(raw)`."""

from dataclasses import dataclass, field
from typing import Any

from app.schemas import OfferIn


@dataclass
class ParseResult:
    """The offers of a raw payload, and one entry {"index", "reason"} per rejected connection (fail soft)."""

    offers: list[OfferIn] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def get_parser(source: str):
    from app.parsers.bahn import BahnParser

    return {BahnParser.source: BahnParser}.get(source, lambda: None)()
