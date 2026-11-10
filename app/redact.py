"""Replace personal values in a raw payload (#1902)."""

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "REDACTED"
EMAIL = re.compile(r"\S+@\S+\.\w+")


def norm(key: str) -> str:
    """Give the key with no case, `_` or `-`."""
    return key.lower().replace("_", "").replace("-", "")


PERSONAL_KEYS = frozenset(
    norm(k)
    for k in (
        "firstName", "lastName", "givenName", "familyName", "surname", "travelerName",
        "travellerName", "passengerName", "fullName", "email", "eMailAddress",
        "emailAddress", "phone", "phoneNumber", "mobile", "dateOfBirth", "birthDate",
        "dob", "bookingCode", "bookingReference", "pnr", "cardNumber",
    )
)


def _string(value: str, url_keep: frozenset[str]) -> str:
    if value.startswith(("http://", "https://")):
        parts = urlsplit(value)
        if parts.query:
            query = [
                (k, v if k in url_keep else REDACTED)
                for k, v in parse_qsl(parts.query, keep_blank_values=True)
            ]
            value = urlunsplit(parts._replace(query=urlencode(query, safe=REDACTED)))
        if EMAIL.search(urlunsplit(urlsplit(value)._replace(query=""))):
            return REDACTED
        return value
    return REDACTED if EMAIL.search(value) else value


def redact(raw: Any, keys: frozenset[str] = PERSONAL_KEYS,
           url_keep: frozenset[str] = frozenset()) -> Any:
    """Give a copy of `raw` with the personal values `REDACTED`; `raw` does not change."""
    keys = frozenset(norm(k) for k in keys)

    def leaf(value: Any) -> Any:
        return _string(value, url_keep) if isinstance(value, str) else value

    def new(value: Any) -> Any:
        if isinstance(value, dict):
            return {}
        if isinstance(value, list):
            return [None] * len(value)
        return leaf(value)

    root = new(raw)
    stack = [(raw, root)]
    while stack:
        src, dst = stack.pop()
        items = src.items() if isinstance(src, dict) else enumerate(src)
        for k, v in items:
            if isinstance(src, dict) and isinstance(k, str) and norm(k) in keys \
                    and not isinstance(v, (dict, list)) and v is not None:
                dst[k] = REDACTED
                continue
            dst[k] = new(v)
            if isinstance(v, (dict, list)):
                stack.append((v, dst[k]))
    return root
