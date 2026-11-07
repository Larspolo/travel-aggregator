"""The export of one trip as a JSON file (#700). `trip_export` gives the data as a dict: the CSV export uses it too."""

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_login
from app.db import get_session
from app.models import Fare, Itinerary, Trip

router = APIRouter()

FORMAT = "travel-aggregator-trip-export"
VERSION = 1


def _local(at: datetime, offset_min: int) -> str:
    """The time in ISO 8601 with the original offset of the leg."""
    return at.astimezone(timezone(timedelta(minutes=offset_min))).isoformat()


def _iso(at: datetime | None) -> str | None:
    return at.isoformat() if at is not None else None


def slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:60].strip("-") or "trip"


def load_trip(session: Session, trip_id: int) -> Trip:
    """The trip with its itineraries, legs, fares and prices, in few queries."""
    trip = session.scalars(
        select(Trip).where(Trip.id == trip_id).options(
            selectinload(Trip.itineraries).selectinload(Itinerary.legs),
            selectinload(Trip.itineraries).selectinload(Itinerary.fares).selectinload(Fare.prices),
        )
    ).one_or_none()
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {trip_id}")
    return trip


def trip_export(trip: Trip, now: datetime | None = None) -> dict:
    """All the stored data of one trip. Money is a string with the exact Decimal value."""
    return {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": (now or datetime.now(timezone.utc)).isoformat(),
        "trip": {
            "id": trip.id, "title": trip.title, "origin": trip.origin_text, "destination": trip.destination_text,
            "date_from": trip.date_from.isoformat() if trip.date_from else None,
            "date_to": trip.date_to.isoformat() if trip.date_to else None,
            "travelers": trip.travelers, "status": trip.status, "notes": trip.notes,
        },
        "itineraries": [
            {
                "id": it.id, "mode_summary": it.mode_summary,
                "depart_at": _iso(it.depart_at), "arrive_at": _iso(it.arrive_at),
                "duration_min": it.duration_min, "transfers": it.transfers,
                "pinned": it.pinned, "hidden": it.hidden, "booked": it.booked, "note": it.note,
                "legs": [
                    {
                        "seq": leg.seq, "mode": leg.mode, "carrier": leg.carrier, "service_no": leg.service_no,
                        "from_name": leg.from_name, "from_code": leg.from_code,
                        "to_name": leg.to_name, "to_code": leg.to_code,
                        "depart_at": _local(leg.depart_at, leg.depart_offset_min),
                        "arrive_at": _local(leg.arrive_at, leg.arrive_offset_min),
                    }
                    for leg in it.legs
                ],
                "fares": [
                    {
                        "source": fare.source, "fare_name": fare.fare_name, "travel_class": fare.travel_class,
                        "flexibility": fare.flexibility, "booking_url": fare.booking_url,
                        "latest_price": str(fare.latest_price), "currency": fare.currency,
                        "latest_captured_at": _iso(fare.latest_captured_at),
                        "prices": [
                            {"captured_at": _iso(p.captured_at), "price": str(p.price), "currency": p.currency}
                            for p in sorted(fare.prices, key=lambda p: (p.captured_at, p.id))
                        ],
                    }
                    for fare in sorted(it.fares, key=lambda f: f.id)
                ],
            }
            for it in sorted(trip.itineraries, key=lambda i: (i.depart_at, i.id))
        ],
    }


@router.get("/trips/{trip_id}/export.json", dependencies=[Depends(require_login)])
def export_json(trip_id: int, session: Session = Depends(get_session)) -> Response:
    trip = load_trip(session, trip_id)
    body = json.dumps(trip_export(trip), ensure_ascii=False, indent=2)
    filename = f"trip-{trip.id}-{slug(trip.title)}.json"
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
