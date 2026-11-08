"""The calendar file of one itinerary of a trip (#781) and the calendar feed of all booked journeys (#1112)."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_login, token_limiter
from app.calendar_feed import feed_token_ok
from app.calendar_ics import feed_ics, itinerary_ics
from app.db import get_session
from app.models import Itinerary, Trip
from app.web.export import slug
from app.web.share import PRIVATE_HEADERS

router = APIRouter()


@router.get("/trips/{trip_id}/itineraries/{itinerary_id}/calendar.ics", dependencies=[Depends(require_login)])
def itinerary_calendar(trip_id: int, itinerary_id: int, session: Session = Depends(get_session)) -> Response:
    itinerary = session.scalars(
        select(Itinerary).where(Itinerary.id == itinerary_id, Itinerary.trip_id == trip_id)
        .options(selectinload(Itinerary.legs))
    ).one_or_none()
    trip = session.get(Trip, trip_id)
    if itinerary is None or trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no itinerary {itinerary_id} in trip {trip_id}")
    filename = f"trip-{trip.id}-{slug(trip.title)}.ics"
    return Response(itinerary_ics(trip, itinerary, datetime.now(timezone.utc)),
                    media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/calendar/{token}.ics")
def calendar_feed(request: Request, token: str, session: Session = Depends(get_session)) -> Response:
    address = request.client.host if request.client else "unknown"
    wait = token_limiter.retry_after(address)
    if wait > 0:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many bad links",
                            headers={**PRIVATE_HEADERS, "Retry-After": str(wait)})
    if len(token) > 100 or not feed_token_ok(session, token):
        token_limiter.failure(address)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no calendar feed", headers=PRIVATE_HEADERS)
    now = datetime.now(timezone.utc)
    itineraries = session.scalars(
        select(Itinerary)
        .where(Itinerary.booked.is_(True), Itinerary.arrive_at >= now - timedelta(days=30))
        .options(selectinload(Itinerary.legs), selectinload(Itinerary.trip))
        .order_by(Itinerary.depart_at, Itinerary.id)
    ).all()
    return Response(feed_ics(list(itineraries), now), media_type="text/calendar; charset=utf-8",
                    headers=PRIVATE_HEADERS)
