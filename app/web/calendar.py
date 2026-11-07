"""The calendar file of one itinerary of a trip (#781): the "Add to calendar" link of a booked row."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_login
from app.calendar_ics import itinerary_ics
from app.db import get_session
from app.models import Itinerary, Trip
from app.web.export import slug

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
