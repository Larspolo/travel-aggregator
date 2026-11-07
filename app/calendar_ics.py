"""iCalendar (RFC 5545) file of one itinerary: one VEVENT per leg (#780).

The text is written by hand: no dependency. Text values come from captures (P5), so the only change is
the escape of RFC 5545 (no HTML).
"""

from datetime import datetime, timedelta, timezone

from app.models import Itinerary, Leg, Trip

CRLF = "\r\n"
MAX_OCTETS = 75


def _escape(text: str) -> str:
    """Escape a text value: backslash, semicolon, comma and a new line."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold(line: str) -> str:
    """Fold a content line to at most 75 octets per physical line, without cutting a character."""
    out: list[str] = []
    current = ""
    current_len = 0
    limit = MAX_OCTETS
    for char in line:
        size = len(char.encode("utf-8"))
        if current_len + size > limit:
            out.append(current)
            current = char
            current_len = size
            limit = MAX_OCTETS - 1  # the continuation line starts with one space
        else:
            current += char
            current_len += size
    out.append(current)
    return (CRLF + " ").join(out)


def _utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _offset_text(offset_min: int) -> str:
    sign = "+" if offset_min >= 0 else "-"
    hours, minutes = divmod(abs(offset_min), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def _local_time(moment: datetime, offset_min: int) -> str:
    local = moment.astimezone(timezone(timedelta(minutes=offset_min)))
    return local.strftime("%H:%M")


def _summary(leg: Leg) -> str:
    prefix_parts = [part for part in (leg.carrier, leg.service_no) if part]
    route = f"{leg.from_name} → {leg.to_name}"
    if prefix_parts:
        return f"{' '.join(prefix_parts)}: {route}"
    return route


def _description(trip: Trip, leg: Leg) -> str:
    lines = [
        f"Departs {_local_time(leg.depart_at, leg.depart_offset_min)} "
        f"({_offset_text(leg.depart_offset_min)}) at {leg.from_name}",
        f"Arrives {_local_time(leg.arrive_at, leg.arrive_offset_min)} "
        f"({_offset_text(leg.arrive_offset_min)}) at {leg.to_name}",
        f"Trip: {trip.title}",
    ]
    return "\n".join(lines)


def _vevent(trip: Trip, leg: Leg, now: datetime) -> list[str]:
    content = [
        "BEGIN:VEVENT",
        f"UID:leg-{leg.id}@travel-aggregator",
        f"DTSTAMP:{_utc(now)}",
        f"DTSTART:{_utc(leg.depart_at)}",
        f"DTEND:{_utc(leg.arrive_at)}",
        f"SUMMARY:{_escape(_summary(leg))}",
        f"LOCATION:{_escape(leg.from_name)}",
        f"DESCRIPTION:{_escape(_description(trip, leg))}",
        "END:VEVENT",
    ]
    return [_fold(line) for line in content]


def itinerary_ics(trip: Trip, itinerary: Itinerary, now: datetime) -> str:
    """Return the calendar file of an itinerary, with CRLF line ends."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//travel-aggregator//trip calendar//EN",
        "CALSCALE:GREGORIAN",
    ]
    lines = [_fold(line) for line in lines]
    for leg in sorted(itinerary.legs, key=lambda item: item.seq):
        lines.extend(_vevent(trip, leg, now))
    lines.append(_fold("END:VCALENDAR"))
    return CRLF.join(lines) + CRLF
