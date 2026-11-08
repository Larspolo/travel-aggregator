"""Search links of a source, built from a URL template and the values of a trip.

The template has the fields {from}, {to} and {date}. Each value is URL-encoded.
The templates, the date format and the place values of each source are in `app/data/search_links.toml`
(read once). This module only builds a string: nothing fetches the link (P1, passive capture).
"""

import tomllib
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, urlsplit, urlunsplit

DATA_FILE = Path(__file__).parent / "data" / "search_links.toml"


@lru_cache(maxsize=1)
def load_sources() -> dict:
    """The sources of the data file, keyed by their table name. Read once."""
    with DATA_FILE.open("rb") as handle:
        return tomllib.load(handle)


def _start_page(template: str) -> str:
    parts = urlsplit(template)
    return urlunsplit((parts.scheme, parts.netloc, "/", "", ""))


def search_link(template: str, trip, date_format: str = "%Y-%m-%d") -> str:
    """Return the search link of `trip` for `template`, or the start page if a value is missing."""
    origin = getattr(trip, "origin_text", None)
    destination = getattr(trip, "destination_text", None)
    date_from = getattr(trip, "date_from", None)
    if not origin or not destination or date_from is None:
        return _start_page(template)
    return template.format(
        **{
            "from": quote(origin, safe=""),
            "to": quote(destination, safe=""),
            "date": quote(date_from.strftime(date_format), safe=""),
        }
    )


def _trip_link(source: dict, trip) -> str | None:
    template = source.get("template")
    places = source.get("places", {})
    origin = places.get(getattr(trip, "origin_text", None) or "")
    destination = places.get(getattr(trip, "destination_text", None) or "")
    if not template or not origin or not destination or getattr(trip, "date_from", None) is None:
        return None
    values = SimpleNamespace(origin_text=origin, destination_text=destination, date_from=trip.date_from)
    return search_link(template, values, source.get("date_format", "%Y-%m-%d"))


def links_by_source(trip) -> dict[str, tuple[str, str | None]]:
    """The (display name, search link or None) of each table of the data file, keyed by its parser source
    (#967); a table with no `source` key is keyed by its table name."""
    return {s.get("source") or key: (s.get("name") or s.get("source") or key, _trip_link(s, trip))
            for key, s in load_sources().items()}


def links_for_trip(trip) -> list[tuple[str, str]]:
    """The (source name, search link) pairs of `trip`. A source with no template, or no value for a place of the trip, gives no link."""
    links = []
    for source in load_sources().values():
        url = _trip_link(source, trip)
        if url:
            links.append((source["name"], url))
    return links
