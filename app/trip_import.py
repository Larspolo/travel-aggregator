"""The import of a trip from the dict of its JSON export (#776), so that the data of a trip can go to another
instance. The keys are those of the ingest: a second import of the same data adds no row. The caller commits."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.derived import Leg as DerivedLeg
from app.derived import derive
from app.ingest import fingerprint
from app.models import Fare, FarePrice, Itinerary, Leg, Trip
from app.schemas import MAX_LEGS, Mode, utc_offset_min
from app.web.export import FORMAT, VERSION

Price = Field(ge=0, max_digits=10, decimal_places=2)
Currency = Field(pattern=r"^[A-Z]{3}$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class TripData(_Model):
    title: str = Field(min_length=1, max_length=200)
    origin: str | None = Field(None, max_length=200)
    destination: str | None = Field(None, max_length=200)
    origin_alt: str | None = Field(None, max_length=200)  # missing in an older export: None (#1422)
    destination_alt: str | None = Field(None, max_length=200)
    date_from: date | None = None
    date_to: date | None = None
    travelers: int = Field(1, ge=1)
    status: str = Field("planning", min_length=1, max_length=20)
    notes: str | None = None
    target_price: Decimal | None = Field(None, gt=0, le=100000)  # missing in an older export: None (#846)
    arrive_by: time | None = None  # missing in an older export: None (#1294)


class LegData(_Model):
    mode: Mode
    carrier: str | None = Field(None, max_length=100)
    service_no: str | None = Field(None, max_length=50)
    from_name: str = Field(min_length=1, max_length=200)
    from_code: str | None = Field(None, max_length=20)
    to_name: str = Field(min_length=1, max_length=200)
    to_code: str | None = Field(None, max_length=20)
    depart_at: AwareDatetime
    arrive_at: AwareDatetime
    ticket: int | None = Field(None, ge=1, le=MAX_LEGS)


class PriceData(_Model):
    captured_at: AwareDatetime
    price: Decimal = Price
    currency: str = Currency


class FareData(_Model):
    source: str = Field(min_length=1, max_length=50)
    fare_name: str | None = Field(None, max_length=100)
    travel_class: str | None = Field(None, max_length=10)
    flexibility: str | None = Field(None, max_length=50)
    booking_url: str | None = Field(None, max_length=2000, pattern=r"^https?://")
    latest_price: Decimal = Price
    currency: str = Currency
    latest_captured_at: AwareDatetime
    reservation_legs: int = Field(0, ge=0, le=MAX_LEGS)  # missing in an older export: 0 (#1625)
    prices: list[PriceData] = Field(default_factory=list)


class ItineraryData(_Model):
    pinned: bool = False
    hidden: bool = False
    booked: bool = False
    note: str | None = None
    # The paid fare (#1150): missing in an older export, so None (no paid price).
    booked_price: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    booked_currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    booked_at: AwareDatetime | None = None
    booked_fare: int | None = Field(None, ge=0)  # the index in `fares`
    # The cancel of the booking and its refund (#1688): missing in an older export, so None.
    cancelled_at: AwareDatetime | None = None
    refund_price: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    # The delay claim (#1691): missing in an older export, so None.
    delay_min: int | None = Field(None, ge=0)
    claim_paid_at: AwareDatetime | None = None
    legs: list[LegData] = Field(min_length=1, max_length=MAX_LEGS)
    fares: list[FareData] = Field(default_factory=list)

    @model_validator(mode="after")
    def _paid_fare_exists(self) -> "ItineraryData":
        if self.booked_fare is not None and self.booked_fare >= len(self.fares):
            raise ValueError(f"booked_fare {self.booked_fare} is not a fare of this itinerary")
        if self.booked_price is not None and self.booked_currency is None:
            raise ValueError("booked_price needs booked_currency")
        return self


class ExportData(_Model):
    format: str
    version: int
    trip: TripData
    itineraries: list[ItineraryData] = Field(default_factory=list)


@dataclass
class ImportResult:
    trip_id: int
    itineraries_added: int = 0
    itineraries_unchanged: int = 0
    fares_added: int = 0
    fares_unchanged: int = 0
    prices_added: int = 0
    prices_unchanged: int = 0


def _self_transfers(legs: list[LegData]) -> int:
    """As `OfferIn.self_transfers` of the ingest: a change of the ticket number between two legs."""
    count, current = 0, legs[0].ticket
    for leg in legs[1:]:
        if leg.ticket is not None and current is not None and leg.ticket != current:
            count += 1
        current = leg.ticket if leg.ticket is not None else current
    return count


def parse_export(data: Any) -> ExportData:
    """Validate the dict of an export. A wrong format, version or field gives a ValueError."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("not a trip export")
    if data.get("version") != VERSION:
        raise ValueError(f"export version {data.get('version')} is not known")
    try:
        return ExportData.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"the trip export is not valid: {exc}") from exc


def _new_itinerary(trip_id: int, d: ItineraryData, fp: str, now: datetime) -> Itinerary:
    der = derive([DerivedLeg(leg.depart_at, leg.arrive_at, leg.mode) for leg in d.legs])
    it = Itinerary(trip_id=trip_id, fingerprint=fp, mode_summary=der.mode_summary, depart_at=d.legs[0].depart_at.astimezone(UTC),
                   arrive_at=d.legs[-1].arrive_at.astimezone(UTC), transfers=der.transfers, duration_min=der.duration_min,
                   first_seen_at=now, last_seen_at=now, pinned=d.pinned, hidden=d.hidden, booked=d.booked,
                   note=d.note)
    it.legs.extend(Leg(seq=seq, mode=leg.mode, carrier=leg.carrier, service_no=leg.service_no,
                       from_name=leg.from_name, from_code=leg.from_code, to_name=leg.to_name, to_code=leg.to_code,
                       depart_at=leg.depart_at.astimezone(UTC), depart_offset_min=utc_offset_min(leg.depart_at),
                       arrive_at=leg.arrive_at.astimezone(UTC), arrive_offset_min=utc_offset_min(leg.arrive_at))
                   for seq, leg in enumerate(d.legs, 1))
    return it


def _restore_paid(it: Itinerary, d: ItineraryData, fare_objs: list[Fare]) -> None:
    """Give the paid price and the paid fare back (#1150). A value the database has already keeps its place."""
    if it.booked_price is None and d.booked_price is not None:
        it.booked_price, it.booked_currency = d.booked_price, d.booked_currency
        it.booked_at = d.booked_at.astimezone(UTC) if d.booked_at is not None else None
    if it.booked_fare_id is None and d.booked_fare is not None:
        it.booked_fare_id = fare_objs[d.booked_fare].id
    if it.cancelled_at is None and d.cancelled_at is not None:
        it.cancelled_at, it.refund_price = d.cancelled_at.astimezone(UTC), d.refund_price
    if it.delay_min is None and d.delay_min is not None:
        it.delay_min = d.delay_min
        it.claim_paid_at = d.claim_paid_at.astimezone(UTC) if d.claim_paid_at is not None else None


def import_trip(session: Session, data: dict, trip_id: int | None = None) -> ImportResult:
    """Make a trip from an export (trip_id None) or add the export to the trip `trip_id`. All the data is validated
    before a row is added, so a bad itinerary stops the whole import. The caller commits."""
    export = parse_export(data)
    if trip_id is None:
        t = export.trip
        trip = Trip(title=t.title, origin_text=t.origin, destination_text=t.destination,
                    origin_alt_text=t.origin_alt, destination_alt_text=t.destination_alt,
                    date_from=t.date_from, date_to=t.date_to, travelers=t.travelers, status=t.status, notes=t.notes,
                    target_price=t.target_price, arrive_by=t.arrive_by)
        session.add(trip)
        session.flush()
    else:
        trip = session.get(Trip, trip_id)
        if trip is None:
            raise ValueError(f"no trip {trip_id}")
    result = ImportResult(trip_id=trip.id)
    now = datetime.now(UTC)
    for d in export.itineraries:
        fp = fingerprint(d.legs)
        it = session.scalar(select(Itinerary).where(Itinerary.trip_id == trip.id, Itinerary.fingerprint == fp))
        if it is None:
            it = _new_itinerary(trip.id, d, fp, now)
            session.add(it)
            result.itineraries_added += 1
        else:
            result.itineraries_unchanged += 1
        fare_objs: list[Fare] = []
        for fd in d.fares:
            fare = next((f for f in it.fares if f.source == fd.source and f.fare_name == fd.fare_name), None)
            if fare is None:
                fare = Fare(source=fd.source, fare_name=fd.fare_name, travel_class=fd.travel_class,
                            flexibility=fd.flexibility, booking_url=fd.booking_url,
                            self_transfers=_self_transfers(d.legs), latest_price=fd.latest_price,
                            currency=fd.currency, latest_captured_at=fd.latest_captured_at,
                            reservation_legs=fd.reservation_legs)
                it.fares.append(fare)
                result.fares_added += 1
            else:
                result.fares_unchanged += 1
            fare_objs.append(fare)
            known = {(p.captured_at, p.price, p.currency) for p in fare.prices}
            for pd in fd.prices:
                if (pd.captured_at, pd.price, pd.currency) in known:
                    result.prices_unchanged += 1
                    continue
                fare.prices.append(FarePrice(price=pd.price, currency=pd.currency, captured_at=pd.captured_at))
                known.add((pd.captured_at, pd.price, pd.currency))
                result.prices_added += 1
            if fare.prices:
                newest = max(fare.prices, key=lambda p: p.captured_at)
                if fare.latest_captured_at is None or newest.captured_at >= fare.latest_captured_at:
                    fare.latest_price, fare.currency, fare.latest_captured_at = (newest.price, newest.currency,
                                                                                  newest.captured_at)
        session.flush()
        _restore_paid(it, d, fare_objs)
    return result
