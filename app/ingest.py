"""Store the offers of POST /api/ingest: one itinerary per journey (by its fingerprint), its legs, a fare per
source and fare name, and a price row per capture. Derived values (duration, transfers) are computed here.
The counts of each case and the raw capture come with `capture:upsert`."""

import gzip
import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.derived import Leg as DerivedLeg
from app.derived import derive
from app.models import Capture, Fare, FarePrice, Itinerary, Leg
from app.schemas import IngestIn, LegIn, OfferIn, utc_offset_min


def fingerprint(legs: list[LegIn]) -> str:
    """The hash of mode, carrier, service number and the UTC times of each leg (docs/SPEC.md section 5)."""
    parts = [f"{leg.mode}|{leg.carrier or ''}|{leg.service_no or ''}|{leg.depart_at.astimezone(UTC).isoformat()}|"
             f"{leg.arrive_at.astimezone(UTC).isoformat()}" for leg in legs]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def store_capture(session: Session, trip_id: int, payload: IngestIn) -> Capture:
    """Add the capture row of one ingest call; `raw` is stored as gzip of its JSON (NULL with no raw). Only the
    fields of P5: no request headers, no cookies. The caller commits; the row id is set after the flush."""
    raw_gz = None if payload.raw is None else gzip.compress(json.dumps(payload.raw, separators=(",", ":")).encode())
    capture = Capture(trip_id=trip_id, source=payload.source, parser_version=payload.parser_version,
                      page_url=payload.page_url, search_context_json=payload.search_context, raw_gz=raw_gz,
                      captured_at=payload.captured_at)
    session.add(capture)
    session.flush()
    return capture


def load_raw(capture: Capture):
    """The raw payload of a capture, as stored by `store_capture` (None when it had no raw)."""
    return None if capture.raw_gz is None else json.loads(gzip.decompress(capture.raw_gz))


def _new_itinerary(trip_id: int, offer: OfferIn, fp: str) -> Itinerary:
    first, last = offer.legs[0], offer.legs[-1]
    d = derive([DerivedLeg(leg.depart_at, leg.arrive_at, leg.mode) for leg in offer.legs])
    it = Itinerary(trip_id=trip_id, fingerprint=fp, mode_summary=d.mode_summary, depart_at=first.depart_at,
                   arrive_at=last.arrive_at, transfers=d.transfers, duration_min=d.duration_min,
                   first_seen_at=datetime.now(UTC), last_seen_at=datetime.now(UTC))
    for seq, leg in enumerate(offer.legs, 1):
        it.legs.append(Leg(seq=seq, mode=leg.mode, carrier=leg.carrier, service_no=leg.service_no,
                           from_name=leg.from_name, from_code=leg.from_code, to_name=leg.to_name, to_code=leg.to_code,
                           depart_at=leg.depart_at, depart_offset_min=utc_offset_min(leg.depart_at),
                           arrive_at=leg.arrive_at, arrive_offset_min=utc_offset_min(leg.arrive_at)))
    return it


def _upsert_one(session: Session, trip_id: int, capture_id: int | None, offer: OfferIn, source: str,
                captured_at: datetime) -> str:
    """Store one offer. Returns "created" (new itinerary), "updated" (known itinerary with a new fare or a changed
    price) or "unchanged". The caller commits."""
    fp = fingerprint(offer.legs)
    it = session.scalar(select(Itinerary).where(Itinerary.trip_id == trip_id, Itinerary.fingerprint == fp))
    result = "unchanged"
    if it is None:
        it = _new_itinerary(trip_id, offer, fp)
        session.add(it)
        result = "created"
    else:
        it.last_seen_at = max(it.last_seen_at, captured_at)
    fare = next((f for f in it.fares if f.source == source and f.fare_name == offer.fare_name), None)
    if fare is None:
        fare = Fare(source=source, fare_name=offer.fare_name, latest_price=offer.price_amount,
                    currency=offer.price_currency, latest_captured_at=captured_at)
        it.fares.append(fare)
    elif fare.latest_price == offer.price_amount and fare.currency == offer.price_currency:
        fare.flexibility, fare.booking_url = offer.flexibility, offer.booking_url
        return result
    if captured_at >= fare.latest_captured_at:
        fare.latest_price, fare.currency, fare.latest_captured_at = (offer.price_amount, offer.price_currency,
                                                                      captured_at)
    fare.flexibility, fare.booking_url = offer.flexibility, offer.booking_url
    fare.prices.append(FarePrice(price=offer.price_amount, currency=offer.price_currency, captured_at=captured_at,
                                 capture_id=capture_id))
    session.flush()
    return "created" if result == "created" else "updated"


def upsert_offers(session: Session, trip_id: int, capture_id: int | None, offers: list[OfferIn], *, source: str,
                  captured_at: datetime) -> dict[str, int]:
    """Upsert the offers, one transaction per offer: one failure does not roll back the others. An itinerary is
    matched by (trip, fingerprint), a fare by (itinerary, source, fare name). A new fare or a changed price adds one
    price row; the same price adds none. A race on the unique constraint is retried once."""
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for offer in offers:
        for attempt in (1, 2):
            try:
                result = _upsert_one(session, trip_id, capture_id, offer, source, captured_at)
                session.commit()
            except IntegrityError:
                session.rollback()
                if attempt == 2:
                    raise
            except Exception:
                session.rollback()
                raise
            else:
                counts[result] += 1
                break
    return counts


def store(session: Session, body: IngestIn) -> dict:
    """Store the valid offers of the body. Returns {"created", "updated", "unchanged", "rejected", "errors"}: the
    errors are the offers that the schema rejected, with their index (#54)."""
    counts = upsert_offers(session, body.trip_id, None, body.offers, source=body.source, captured_at=body.captured_at)
    return {**counts, "rejected": len(body.offer_errors), "errors": body.offer_errors}
