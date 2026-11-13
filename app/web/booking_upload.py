"""Mark the matching itinerary of a trip as booked from an uploaded confirmation e-mail (#2297).

The mail is untrusted data (P5): the route stores nothing of it, only the booked state of the itinerary."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth import require_login, verify_csrf
from app.booking_mail import MailBooking, read_booking
from app.db import get_session
from app.ingest import service_key
from app.models import Itinerary, Trip
from app.schemas import MAX_MAIL_BYTES
from app.web.manual import LEG_FIELDS, MAX_FORM_LEGS, _page
from app.web.pages import _get_trip, keep_paid_fare

router = APIRouter()

CODE_MAX = 40
NO_MATCH = "No itinerary of this trip matches the reservation"


def _minute(t: datetime | None) -> datetime | None:
    return None if t is None else t.replace(second=0, microsecond=0)


def _matches(it: Itinerary, booking: MailBooking) -> bool:
    legs = sorted(it.legs, key=lambda x: x.seq)
    if len(legs) != len(booking.legs):
        return False
    for leg, mail in zip(legs, booking.legs):
        if _minute(leg.depart_at) != _minute(mail.depart_at) or _minute(leg.arrive_at) != _minute(mail.arrive_at):
            return False
        a, b = service_key(leg.service_no), service_key(mail.number)
        if a and b and a != b:
            return False
    return True


def _mark(session: Session, trip, booking: MailBooking) -> str:
    match = next((it for it in trip.itineraries if _matches(it, booking)), None)
    if match is None:
        return NO_MATCH
    first = sorted(match.legs, key=lambda x: x.seq)[0]
    name = f"{first.from_name} – {first.to_name} {first.depart_at:%Y-%m-%d %H:%M} UTC"
    if match.booked:
        return f"{name} is already booked: nothing changed"
    match.booked = True
    match.cancelled_at = match.refund_price = None
    keep_paid_fare(session, match)
    if booking.price is not None:
        match.booked_price, match.booked_currency = booking.price, booking.currency
    match.booking_code = booking.code[:CODE_MAX] if booking.code else None
    session.commit()
    price = f"{match.booked_price} {match.booked_currency or ''}".strip() if match.booked_price is not None else "-"
    return f"Marked {name} as booked: paid {price}, code {match.booking_code or '-'}"


def _offset_text(offset: timedelta) -> str:
    minutes = int(offset.total_seconds()) // 60
    sign = "-" if minutes < 0 else "+"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def _form_values(trip: Trip, booking: MailBooking) -> dict:
    """The manual form filled with the reservation (#2298). All times show the offset of the first leg."""
    offset = booking.legs[0].depart_at.utcoffset()
    local = timezone(offset)

    def time_text(t: datetime | None) -> str:
        return "" if t is None else t.astimezone(local).strftime("%Y-%m-%dT%H:%M")

    values = {f"leg{i}_{k}": "" for i in range(MAX_FORM_LEGS) for k in LEG_FIELDS}
    values |= {"price_amount": "" if booking.price is None else str(booking.price),
               "price_currency": booking.currency or "EUR", "utc_offset": _offset_text(offset),
               "travelers": str(trip.travelers or 1), "fare_name": "", "booking_url": "", "travel_class": ""}
    for i, leg in enumerate(booking.legs[:MAX_FORM_LEGS]):
        values |= {f"leg{i}_mode": leg.mode, f"leg{i}_from_name": leg.origin or "",
                   f"leg{i}_to_name": leg.destination or "", f"leg{i}_depart_at": time_text(leg.depart_at),
                   f"leg{i}_arrive_at": time_text(leg.arrive_at), f"leg{i}_carrier": leg.carrier or "",
                   f"leg{i}_service_no": leg.number or ""}
    return values


@router.post("/trips/{trip_id}/booking-mail", dependencies=[Depends(require_login), Depends(verify_csrf)])
async def upload_booking_mail(request: Request, trip_id: int, file: UploadFile | None = File(None),
                              session: Session = Depends(get_session)) -> Response:
    trip = _get_trip(session, trip_id)
    raw = await file.read(MAX_MAIL_BYTES + 1) if file is not None else b""
    if len(raw) > MAX_MAIL_BYTES:
        message = "The e-mail is too large"
    else:
        booking = read_booking(raw) if raw else None
        if booking is not None and booking.legs and not any(_matches(it, booking) for it in trip.itineraries):
            # no itinerary matches: the manual form opens with the reservation, the owner saves it (#2298)
            return _page(request, trip_id, _form_values(trip, booking), [NO_MATCH])
        message = "No reservation found in this e-mail" if booking is None else _mark(session, trip, booking)
    request.session["flash"] = message
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)
