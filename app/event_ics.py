"""Reader of the first event of an iCalendar (RFC 5545) file (#2493).

The text is read by hand: no dependency (the writer `app/calendar_ics.py` is the style). The file comes from
the owner's upload (P5): the values are text only, cut to 200 characters.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MAX_BYTES = 256 * 1024
MAX_TEXT = 200
_DURATION = re.compile(r"^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


class EventError(ValueError):
    """A file that gives no event; `reason` is a text for the form."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class EventFields:
    summary: str | None
    location: str | None
    start: datetime | date
    end: datetime | date
    utc: bool


def _unfold(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n[ \t]", "", text).split("\n")


def _unescape(value: str) -> str:
    return re.sub(
        r"\\(.)", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value
    )


def _split(line: str) -> tuple[str, dict[str, str], str]:
    """Split a content line into its name, its parameters and its value (a colon in a quoted value stays)."""
    in_quote = False
    for i, char in enumerate(line):
        if char == '"':
            in_quote = not in_quote
        elif char == ":" and not in_quote:
            head, value = line[:i], line[i + 1 :]
            break
    else:
        return line.upper(), {}, ""
    name, *params = head.split(";")
    parsed = {}
    for param in params:
        key, _, val = param.partition("=")
        parsed[key.upper()] = val.strip('"')
    return name.upper(), parsed, value


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    text = _unescape(value).strip()
    return text[:MAX_TEXT] or None


def _zone(name: str | None) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _parse_time(params: dict[str, str], value: str) -> datetime | date:
    value = value.strip()
    try:
        if params.get("VALUE", "").upper() == "DATE" or len(value) == 8:
            return datetime.strptime(value, "%Y%m%d").date()
        if value.endswith("Z"):
            return datetime.strptime(value[:-1], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return datetime.strptime(value, "%Y%m%dT%H%M%S")
    except ValueError as exc:
        raise EventError("The event has a time that is not correct.") from exc


def _duration(value: str) -> timedelta:
    match = _DURATION.match(value.strip().upper())
    if not match or value.strip().upper() in {"P", "PT"}:
        raise EventError("The event has a duration that is not correct.")
    sign, weeks, days, hours, minutes, seconds = match.groups()
    delta = timedelta(
        weeks=int(weeks or 0), days=int(days or 0), hours=int(hours or 0),
        minutes=int(minutes or 0), seconds=int(seconds or 0),
    )
    return -delta if sign == "-" else delta


def read_event(data: bytes, now: datetime) -> EventFields:
    """Read the first VEVENT of `data`; `now` is aware. Raise `EventError` with a reason for the form."""
    if len(data) > MAX_BYTES:
        raise EventError("The file is larger than 256 kB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise EventError("The file is not UTF-8 text.") from exc

    calendar_zone: str | None = None
    props: dict[str, tuple[dict[str, str], str]] = {}
    depth = 0  # nested components in the event (VALARM)
    in_event = found = False
    for line in _unfold(text):
        if not line.strip():
            continue
        name, params, value = _split(line)
        upper = value.strip().upper()
        if not in_event:
            if name == "X-WR-TIMEZONE" and calendar_zone is None:
                calendar_zone = value.strip()
            elif name == "BEGIN" and upper == "VEVENT":
                in_event = found = True
            continue
        if name == "BEGIN":
            depth += 1
        elif name == "END":
            if depth:
                depth -= 1
            elif upper == "VEVENT":
                break
        elif depth == 0 and name not in props:
            props[name] = (params, value)
    if not found:
        raise EventError("The file has no event.")
    if "DTSTART" not in props:
        raise EventError("The event has no start.")

    start_params, start_value = props["DTSTART"]
    start = _parse_time(start_params, start_value)
    if "DTEND" in props:
        end = _parse_time(*props["DTEND"])
    elif "DURATION" in props:
        end = start + _duration(props["DURATION"][1])
    else:
        end = start
    all_day = not isinstance(start, datetime)
    if all_day:
        if isinstance(end, datetime):
            end = end.date()
        if "DTEND" in props or "DURATION" in props:
            end = max(start, end - timedelta(days=1))
        if start < now.astimezone(timezone.utc).date():
            raise EventError("The event starts in the past.")
        return EventFields(_text(_val(props, "SUMMARY")), _text(_val(props, "LOCATION")), start, end, False)

    utc = False
    wall_zone = _zone(start_params.get("TZID"))
    if start.tzinfo is not None:
        local = _zone(calendar_zone)
        utc = local is None
        moment = start
        start = start.astimezone(local or timezone.utc).replace(tzinfo=None)
        if isinstance(end, datetime) and end.tzinfo is not None:
            end = end.astimezone(local or timezone.utc).replace(tzinfo=None)
    elif wall_zone is not None:
        moment = start.replace(tzinfo=wall_zone)
    else:
        moment = start.replace(tzinfo=now.tzinfo or timezone.utc)
    if isinstance(end, date) and not isinstance(end, datetime):
        end = datetime.combine(end, datetime.min.time())
    if end < start:
        end = start
    if moment < now:
        raise EventError("The event starts in the past.")
    return EventFields(_text(_val(props, "SUMMARY")), _text(_val(props, "LOCATION")), start, end, utc)


def _val(props: dict[str, tuple[dict[str, str], str]], name: str) -> str | None:
    return props[name][1] if name in props else None
