"""Search links of a source, built from a URL template and the values of a trip.

The template has the fields {from}, {to} and {date} (ISO date). Each value is URL-encoded.
This module only builds a string: nothing fetches the link (P1, passive capture).
"""

from urllib.parse import quote, urlsplit, urlunsplit


def _start_page(template: str) -> str:
    parts = urlsplit(template)
    return urlunsplit((parts.scheme, parts.netloc, "/", "", ""))


def search_link(template: str, trip) -> str:
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
            "date": quote(date_from.isoformat(), safe=""),
        }
    )
