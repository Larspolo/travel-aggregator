"""Ingest helpers: the itinerary fingerprint (SPEC section 5)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone


def _utc_instant(value: str) -> str:
    """Return the instant of an ISO 8601 timestamp as UTC, so the offset does not matter."""
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError(f"timestamp must be timezone-aware: {value!r}")
    return moment.astimezone(timezone.utc).isoformat()


def fingerprint(legs: Sequence[Mapping[str, object]]) -> str:
    """Return the hex SHA-256 of the identity of an itinerary.

    The identity is mode, carrier, service number, departure and arrival instant of every leg, in
    order. Price, fare name, booking URL and place names are not part of it.
    """
    identity = [
        [
            leg["mode"],
            leg["carrier"],
            leg["service_no"],
            _utc_instant(str(leg["depart_at"])),
            _utc_instant(str(leg["arrive_at"])),
        ]
        for leg in legs
    ]
    encoded = json.dumps(identity, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
