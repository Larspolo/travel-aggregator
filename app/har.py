"""Read the search entries of a HAR file into raw payloads (#1562).

Each parser has the hosts and URL paths that its userscript reads (`hosts`, `paths`). An entry gives the raw form that
the userscript sends; a parser with `har_raw(url, method, request, response)` shapes it, else it is
{url, method, request, response}. Only the URL, the method, the request body and the response body are read: never
the headers or cookies (P5).
"""

import base64
import binascii
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from app.parsers import parser_classes


class HarError(ValueError):
    """The file is not a HAR file."""


@dataclass
class HarResult:
    items: list[tuple[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)


def source_of(url: str) -> type | None:
    """The parser class whose host and path rule matches the URL, else None."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    for cls in parser_classes().values():
        if parts.hostname in cls.hosts and parts.path in cls.paths:
            return cls
    return None


def _json(text: Any, encoding: Any) -> Any:
    if not isinstance(text, str):
        raise ValueError("no text")
    if encoding == "base64":
        text = base64.b64decode(text, validate=True).decode("utf-8")
    return json.loads(text)


def read_har(har: Any) -> HarResult:
    """(source, raw payload) of each entry whose URL a parser reads; a skipped supported entry has a reason."""
    if isinstance(har, (str, bytes)):
        try:
            har = json.loads(har)
        except ValueError as e:
            raise HarError(f"the file is not JSON: {e}") from None
    log = har.get("log") if isinstance(har, dict) else None
    entries = log.get("entries") if isinstance(log, dict) else None
    if not isinstance(entries, list):
        raise HarError("the file has no log.entries list")
    result = HarResult()
    for i, entry in enumerate(entries):
        request = entry.get("request") if isinstance(entry, dict) else None
        response = entry.get("response") if isinstance(entry, dict) else None
        url = request.get("url") if isinstance(request, dict) else None
        cls = source_of(url) if isinstance(url, str) else None
        if cls is None:
            continue
        method = request.get("method") if isinstance(request.get("method"), str) else "GET"
        content = response.get("content") if isinstance(response, dict) else None
        content = content if isinstance(content, dict) else {}
        try:
            body = _json(content.get("text"), content.get("encoding"))
        except (ValueError, binascii.Error, UnicodeDecodeError) as e:
            result.skipped.append({"index": i, "source": cls.source, "reason": f"the response is not JSON: {e}"[:200]})
            continue
        post = request.get("postData")
        try:
            sent = _json(post.get("text"), None) if isinstance(post, dict) else None
        except ValueError:
            sent = None
        shape = getattr(cls, "har_raw", None)
        raw = shape(url, method, sent, body) if shape else {"url": url, "method": method, "request": sent, "response": body}
        if raw is None:
            result.skipped.append({"index": i, "source": cls.source, "reason": "not a search request of the source"})
            continue
        result.items.append((cls.source, raw))
    return result
