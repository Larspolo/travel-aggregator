"""The export of one trip as a JSON file (#700) or a CSV file (#701). `trip_export` gives the data as a dict."""

import csv
import io
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
from app.spend import YEAR_CSV_COLUMNS

router = APIRouter()

FORMAT = "travel-aggregator-trip-export"
VERSION = 1


def _local(at: datetime, offset_min: int) -> str:
    """The time in ISO 8601 with the original offset of the leg."""
    return at.astimezone(timezone(timedelta(minutes=offset_min))).isoformat()


def _iso(at: datetime | None) -> str | None:
    return at.isoformat() if at is not None else None


def _paid_index(it: Itinerary) -> int | None:
    """The position of the paid fare in the `fares` list of the export (#1150), or None."""
    if it.booked_fare_id is None:
        return None
    for index, fare in enumerate(sorted(it.fares, key=lambda f: f.id)):
        if fare.id == it.booked_fare_id:
            return index
    return None


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
            "origin_alt": trip.origin_alt_text, "destination_alt": trip.destination_alt_text,
            "date_from": trip.date_from.isoformat() if trip.date_from else None,
            "date_to": trip.date_to.isoformat() if trip.date_to else None,
            "travelers": trip.travelers, "status": trip.status, "notes": trip.notes,
            "target_price": str(trip.target_price) if trip.target_price is not None else None,
            "arrive_by": trip.arrive_by.strftime("%H:%M") if trip.arrive_by else None,
        },
        "itineraries": [
            {
                "id": it.id, "mode_summary": it.mode_summary,
                "depart_at": _iso(it.depart_at), "arrive_at": _iso(it.arrive_at),
                "duration_min": it.duration_min, "transfers": it.transfers,
                "pinned": it.pinned, "hidden": it.hidden, "booked": it.booked, "note": it.note,
                "booked_price": str(it.booked_price) if it.booked_price is not None else None,
                "booked_currency": it.booked_currency, "booked_at": _iso(it.booked_at),
                "booked_fare": _paid_index(it),
                "cancelled_at": _iso(it.cancelled_at),
                "refund_price": str(it.refund_price) if it.refund_price is not None else None,
                "delay_min": it.delay_min, "claim_paid_at": _iso(it.claim_paid_at),
                "booking_code": it.booking_code,
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
                        "reservation_legs": fare.reservation_legs,
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


CSV_COLUMNS = [
    "route", "departure", "arrival", "duration_min", "transfers", "modes", "carriers", "service_numbers",
    "source", "fare_name", "travel_class", "latest_price", "currency", "last_captured", "pinned", "hidden",
    "booked", "note", "booking_url", "paid",
]
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: object) -> str:
    """A text cell. A value that a spreadsheet could run as a formula gets a leading quote (CSV injection)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


def _join(values) -> str:
    """The distinct non-empty values in their order, joined for one cell."""
    return "; ".join(dict.fromkeys(v for v in values if v))


def csv_rows(data: dict) -> list[list[object]]:
    """One row per fare, built from the `trip_export` dict."""
    rows = []
    for it in data["itineraries"]:
        legs = sorted(it["legs"], key=lambda leg: leg["seq"])
        first, last = (legs[0], legs[-1]) if legs else ({}, {})
        for index, fare in enumerate(it["fares"]):
            paid = it["booked_price"] if index == it["booked_fare"] else None
            rows.append([
                f"{first.get('from_name') or ''} - {last.get('to_name') or ''}",
                first.get("depart_at") or it["depart_at"] or "",
                last.get("arrive_at") or it["arrive_at"] or "",
                it["duration_min"], it["transfers"],
                _join(leg["mode"] for leg in legs),
                _join(leg["carrier"] for leg in legs),
                _join(leg["service_no"] for leg in legs),
                fare["source"], fare["fare_name"], fare["travel_class"],
                fare["latest_price"], fare["currency"], fare["latest_captured_at"],
                it["pinned"], it["hidden"], it["booked"], it["note"], fare["booking_url"], paid or "",
            ])
    return rows


def trip_csv(data: dict) -> bytes:
    """The CSV file as UTF-8 with a byte order mark, so that a spreadsheet reads the text correctly."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for row in csv_rows(data):
        writer.writerow([_cell(value) for value in row])
    return ("﻿" + out.getvalue()).encode("utf-8")


def year_csv(rows: list[list[object]]) -> bytes:
    """The CSV file of one year of "Travel per year" as UTF-8 with a byte order mark (#1730)."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(YEAR_CSV_COLUMNS)
    for row in rows:
        writer.writerow([_cell(value) for value in row])
    return ("﻿" + out.getvalue()).encode("utf-8")


@router.get("/trips/{trip_id}/export.csv", dependencies=[Depends(require_login)])
def export_csv(trip_id: int, session: Session = Depends(get_session)) -> Response:
    trip = load_trip(session, trip_id)
    filename = f"trip-{trip.id}-{slug(trip.title)}.csv"
    return Response(trip_csv(trip_export(trip)), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
