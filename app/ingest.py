"""Store the offers of POST /api/ingest: one itinerary per journey (by its fingerprint), its legs, a fare per
source and fare name, and a price row per capture. Derived values (duration, transfers) are computed here.
The counts of each case and the raw capture come with `capture:upsert`."""

import hashlib
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fare, FarePrice, Itinerary, Leg
from app.schemas import IngestIn, LegIn, OfferIn, utc_offset_min


def fingerprint(legs: list[LegIn]) -> str:
    """The hash of mode, carrier, service number and the UTC times of each leg (docs/SPEC.md section 5)."""
    parts = [f"{leg.mode}|{leg.carrier or ''}|{leg.service_no or ''}|{leg.depart_at.astimezone(UTC).isoformat()}|"
             f"{leg.arrive_at.astimezone(UTC).isoformat()}" for leg in legs]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _new_itinerary(trip_id: int, offer: OfferIn, fp: str) -> Itinerary:
    first, last = offer.legs[0], offer.legs[-1]
    modes = list(dict.fromkeys(leg.mode for leg in offer.legs))
    it = Itinerary(trip_id=trip_id, fingerprint=fp, mode_summary="+".join(modes), depart_at=first.depart_at,
                   arrive_at=last.arrive_at, transfers=len(offer.legs) - 1,
                   duration_min=int((last.arrive_at - first.depart_at).total_seconds() // 60))
    for seq, leg in enumerate(offer.legs, 1):
        it.legs.append(Leg(seq=seq, mode=leg.mode, carrier=leg.carrier, service_no=leg.service_no,
                           from_name=leg.from_name, from_code=leg.from_code, to_name=leg.to_name, to_code=leg.to_code,
                           depart_at=leg.depart_at, depart_offset_min=utc_offset_min(leg.depart_at),
                           arrive_at=leg.arrive_at, arrive_offset_min=utc_offset_min(leg.arrive_at)))
    return it


def store(session: Session, body: IngestIn) -> dict[str, int]:
    """Store the offers of the body in one transaction. Returns {"created": new itineraries, "updated": known ones}."""
    created = updated = 0
    for offer in body.offers:
        fp = fingerprint(offer.legs)
        it = session.scalar(select(Itinerary).where(Itinerary.trip_id == body.trip_id, Itinerary.fingerprint == fp))
        if it is None:
            it = _new_itinerary(body.trip_id, offer, fp)
            session.add(it)
            created += 1
        else:
            it.last_seen_at = max(it.last_seen_at, body.captured_at)
            updated += 1
        fare = next((f for f in it.fares if f.source == body.source and f.fare_name == offer.fare_name), None)
        if fare is None:
            fare = Fare(source=body.source, fare_name=offer.fare_name, latest_price=offer.price_amount,
                        currency=offer.price_currency, latest_captured_at=body.captured_at)
            it.fares.append(fare)
        if body.captured_at >= fare.latest_captured_at:
            fare.latest_price, fare.currency, fare.latest_captured_at = (offer.price_amount, offer.price_currency,
                                                                          body.captured_at)
            fare.flexibility, fare.booking_url = offer.flexibility, offer.booking_url
        fare.prices.append(FarePrice(price=offer.price_amount, currency=offer.price_currency, captured_at=body.captured_at))
        session.flush()        # the next offer of the batch finds this itinerary by its fingerprint
    session.commit()
    return {"created": created, "updated": updated}
