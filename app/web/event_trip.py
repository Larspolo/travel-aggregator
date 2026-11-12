"""Make a trip and its return trip from an uploaded calendar event (#2494).

The file is untrusted data (P5): `read_event()` gives text only, cut to 200 characters."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login, verify_csrf
from app.db import get_session
from app.event_ics import MAX_BYTES, EventError, read_event
from app.models import Trip
from app.web.pages import _form_page

router = APIRouter()

UTC_NOTE = "The event file gave UTC times: check the arrive-by and leave-after times."


def clock() -> datetime:
    """The aware time now; a test replaces it."""
    return datetime.now().astimezone()


def _margin(text: str | None) -> int:
    text = (text or "").strip() or "60"
    if not text.isdigit() or not 0 <= int(text) <= 600:
        raise EventError("The margin must be a whole number of minutes from 0 to 600.")
    return int(text)


@router.post("/trips/from-event", dependencies=[Depends(require_login), Depends(verify_csrf)])
async def trip_from_event(request: Request, file: UploadFile | None = File(None), origin_text: str = Form(""),
                          margin: str = Form("60"), session: Session = Depends(get_session)):
    origin = origin_text.strip()[:200] or None
    try:
        minutes = _margin(margin)
        raw = await file.read(MAX_BYTES + 1) if file is not None else b""
        if not raw:
            raise EventError("Select an .ics file.")
        event = read_event(raw, clock())
    except EventError as exc:
        values = {"travelers": 1, "status": "planning", "origin_text": origin or ""}
        return _form_page(request, values, [str(exc)], None, session, code=422)
    title = event.summary or "Event"
    trip = Trip(title=title, origin_text=origin, destination_text=event.location, status="planning")
    back = Trip(title=f"{title[:191]} (return)", origin_text=event.location, destination_text=origin,
                status="planning", return_of=trip)
    if isinstance(event.start, datetime):
        arrive = event.start - timedelta(minutes=minutes)
        trip.date_from = trip.date_to = arrive.date()
        trip.arrive_by = arrive.time()
        back.date_from = back.date_to = event.end.date()
        back.leave_after = event.end.time()
    else:
        trip.date_from = trip.date_to = event.start
        back.date_from = back.date_to = event.end
    session.add_all([trip, back])
    session.commit()
    if event.utc:
        request.session["flash"] = UTC_NOTE
    return RedirectResponse(f"/trips/{trip.id}/edit", status_code=303)
