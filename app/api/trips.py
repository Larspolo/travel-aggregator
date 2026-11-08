"""GET and POST /api/trips: the trips of the userscript dropdown, and a new trip (docs/SPEC.md section 5)."""

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_token
from app.db import get_session
from app.models import Trip
from app.schemas import TripStatus

router = APIRouter(dependencies=[Depends(require_token)])


class TripIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    origin_text: str | None = Field(None, max_length=200)
    destination_text: str | None = Field(None, max_length=200)
    date_from: date | None = None
    date_to: date | None = None
    travelers: int = Field(1, ge=1, le=20)
    notes: str | None = Field(None, max_length=5000)
    status: TripStatus = "planning"

    @model_validator(mode="after")
    def _dates_in_order(self) -> "TripIn":
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("date_to is before date_from")
        return self


class TripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    origin_text: str | None
    destination_text: str | None
    date_from: date | None
    date_to: date | None
    travelers: int
    status: str


@router.get("/trips")
def list_trips(status_filter: str | None = Query(None, alias="status", max_length=20),
               session: Session = Depends(get_session)) -> list[TripOut]:
    """All trips, newest first; `?status=planning` only those of one status."""
    query = select(Trip).order_by(Trip.created_at.desc(), Trip.id.desc())
    if status_filter:
        query = query.where(Trip.status == status_filter)
    return [TripOut.model_validate(t) for t in session.scalars(query)]


@router.post("/trips", status_code=status.HTTP_201_CREATED)
def create_trip(body: TripIn, session: Session = Depends(get_session)) -> TripOut:
    trip = Trip(**body.model_dump())
    session.add(trip)
    session.commit()
    return TripOut.model_validate(trip)
