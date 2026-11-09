"""The travel-day message of a booked itinerary (#1648): the itineraries that need it, and the mark once sent.

An itinerary is due when it is booked, not yet sent, departs after `now` and at most H hours later, and its trip is
not archived. H = 0 (or no setting) turns the messages off. All times are UTC.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendar_ics import _summary
from app.models import Itinerary, Trip
from app.notify import _money, alert_messages, deliver, setting

TRAVEL_DAY_HOURS_KEY = "travel_day_hours"
MAX_TRAVEL_DAY_HOURS = 72  # the setting on the messages settings page (#1650)


def _hours(session: Session) -> int:
    try:
        return max(0, int(setting(session, TRAVEL_DAY_HOURS_KEY, "0")))
    except ValueError:
        return 0


def due_travel_days(session: Session, now: datetime) -> list[Itinerary]:
    """The booked itineraries whose travel-day message is due at `now` (timezone-aware), ordered by departure."""
    h = _hours(session)
    if h == 0:
        return []
    now = now.astimezone(timezone.utc)
    query = (
        select(Itinerary)
        .join(Trip, Trip.id == Itinerary.trip_id)
        .where(
            Itinerary.booked.is_(True),
            Itinerary.travel_day_sent_at.is_(None),
            Itinerary.depart_at > now,
            Itinerary.depart_at <= now + timedelta(hours=h),
            Trip.status != "archived",
        )
        .order_by(Itinerary.depart_at, Itinerary.id)
    )
    return list(session.scalars(query))


def mark_sent(itinerary: Itinerary, now: datetime) -> None:
    """Store the time of the travel-day message of `itinerary`; the caller commits."""
    itinerary.travel_day_sent_at = now.astimezone(timezone.utc)


def _label(depart_local: datetime, now_local: datetime) -> str:
    if depart_local.date() == now_local.date():
        return "Today"
    if depart_local.date() == now_local.date() + timedelta(days=1):
        return "Tomorrow"
    return f"{depart_local:%a} {depart_local.day} {depart_local:%b}"


def _local(moment: datetime, offset_min: int) -> datetime:
    return moment.astimezone(timezone(timedelta(minutes=offset_min)))


def _message(it: Itinerary, now: datetime, base_url: str) -> tuple[str, str, str]:
    """The title, the text and the click link of the travel-day message of `it` (its legs have local times)."""
    first, last = it.legs[0], it.legs[-1]
    depart_local = _local(first.depart_at, first.depart_offset_min)
    arrive_local = _local(last.arrive_at, last.arrive_offset_min)
    title = (f"{_label(depart_local, _local(now, first.depart_offset_min))} {depart_local:%H:%M} "
             f"{first.from_name} → {arrive_local:%H:%M} {last.to_name}")
    lines: list[str] = []
    for i, leg in enumerate(it.legs):
        if i:
            lines.append(f"change in {leg.from_name}")
        d = _local(leg.depart_at, leg.depart_offset_min)
        a = _local(leg.arrive_at, leg.arrive_offset_min)
        lines.append(f"{_summary(leg)} {d:%H:%M} → {a:%H:%M}")
    if it.booked_price is not None:
        lines.append(f"Paid {_money(it.booked_price)} {it.booked_currency or ''}".rstrip())
    click = f"{base_url.rstrip('/')}/upcoming?only={it.id}" if base_url else ""
    if click:
        lines.append(click)
    return title, "\n".join(lines), click


def send_travel_days(session: Session, now: datetime, base_url: str) -> int:
    """Send the travel-day message of each due itinerary by the active channel, and mark it. Return the count.

    The channel `none` sends nothing and marks nothing. An itinerary with no leg has nothing to show: it is marked
    and not sent. No request goes to a travel site (P1).
    """
    now = now.astimezone(timezone.utc)
    sent = 0
    for it in due_travel_days(session, now):
        if not it.legs:
            mark_sent(it, now)
            session.commit()
            continue
        title, text, click = _message(it, now, base_url)
        msgs = alert_messages(session, title, text, click)
        if not msgs:
            break
        deliver(msgs)
        mark_sent(it, now)
        session.commit()
        sent += 1
    return sent
