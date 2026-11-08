"""Store the offers of POST /api/ingest: one itinerary per journey (by its fingerprint), its legs, a fare per
source and fare name, and a price row per capture. Derived values (duration, transfers) are computed here.
The counts of each case and the raw capture come with `capture:upsert`."""

import gzip
import hashlib
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.derived import Leg as DerivedLeg
from app.derived import derive
from app.models import Capture, Fare, FarePrice, Itinerary, Leg, Trip
from app.parsers import count, get_parser
from app.parsers.ns import CHANGE_STATION
from app.tripmatch import best_trip, mismatch, suggest_trip, travelers_text
from app.retention import delete_old_captures, retention_days
from app.schemas import IngestIn, LegIn, OfferIn, utc_offset_min
from app.notify import PriceDrop
from app.currency import load_rates, to_eur

log = logging.getLogger(__name__)


def service_key(service_no: str | None) -> str:
    """The service number in one form for all sources (#481): upper case, no spaces ("ICE 121" gives "ICE121")."""
    return "".join((service_no or "").split()).upper()


def fingerprint(legs: list[LegIn]) -> str:
    """The hash of the journey key (#481, docs/SPEC.md section 5): the mode and the normalized service number of each
    leg, the UTC time of the first departure and of the last arrival. The carrier and the times of the legs between
    do not count, so the same train from two sources (bahn.de, NS International) gives one itinerary."""
    parts = [f"{leg.mode}|{service_key(leg.service_no)}" for leg in legs]
    parts += [legs[0].depart_at.astimezone(UTC).isoformat(), legs[-1].arrive_at.astimezone(UTC).isoformat()]
    return hashlib.sha256(("journey\n" + "\n".join(parts)).encode()).hexdigest()


def has_real_legs(legs) -> bool:
    """True when each leg has its own stations and times: no leg goes to or from an unknown change station of the
    NS International parser (only the journey start and end are real there)."""
    return all(CHANGE_STATION not in (leg.from_name, leg.to_name) for leg in legs)


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


def _legs(offer: OfferIn) -> list[Leg]:
    return [Leg(seq=seq, mode=leg.mode, carrier=leg.carrier, service_no=leg.service_no, from_name=leg.from_name,
                from_code=leg.from_code, to_name=leg.to_name, to_code=leg.to_code, depart_at=leg.depart_at,
                depart_offset_min=utc_offset_min(leg.depart_at), arrive_at=leg.arrive_at,
                arrive_offset_min=utc_offset_min(leg.arrive_at))
            for seq, leg in enumerate(offer.legs, 1)]


def _new_itinerary(trip_id: int, offer: OfferIn, fp: str) -> Itinerary:
    first, last = offer.legs[0], offer.legs[-1]
    d = derive([DerivedLeg(leg.depart_at, leg.arrive_at, leg.mode) for leg in offer.legs])
    it = Itinerary(trip_id=trip_id, fingerprint=fp, mode_summary=d.mode_summary, depart_at=first.depart_at,
                   arrive_at=last.arrive_at, transfers=d.transfers, duration_min=d.duration_min,
                   first_seen_at=datetime.now(UTC), last_seen_at=datetime.now(UTC))
    it.legs.extend(_legs(offer))
    return it


def _replace_legs(session: Session, it: Itinerary, offer: OfferIn) -> None:
    """Give a stored itinerary the real legs of an offer of the same journey (#484). The journey key keeps the
    first departure, the last arrival, the modes and the count of legs, so the derived values stay the same."""
    it.legs.clear()
    session.flush()  # delete the old legs first: the new legs use the same (itinerary_id, seq)
    it.legs.extend(_legs(offer))


def _crosses_target(session: Session, trip_id: int, old: tuple | None, offer: OfferIn) -> bool:
    """The new price (in EUR) is at or below the target of the trip, and the fare is new or its old latest price
    was above the target (#848). A fare with no rate does not cross."""
    trip = session.get(Trip, trip_id)
    if trip is None or trip.target_price is None:
        return False
    rates = load_rates(session)
    new_eur = to_eur(offer.price_amount, offer.price_currency, rates)
    if new_eur is None or new_eur > trip.target_price:
        return False
    if old is None:
        return True
    old_eur = to_eur(old[0], old[1], rates)
    return old_eur is not None and old_eur > trip.target_price


def _upsert_one(session: Session, trip_id: int, capture_id: int | None, offer: OfferIn, source: str,
                captured_at: datetime, drops: list | None = None) -> str:
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
        if not has_real_legs(it.legs) and has_real_legs(offer.legs):
            _replace_legs(session, it, offer)
    fare = next((f for f in it.fares if f.source == source and f.fare_name == offer.fare_name), None)
    old = None if fare is None else (fare.latest_price, fare.currency)
    if fare is None:
        fare = Fare(source=source, fare_name=offer.fare_name, latest_price=offer.price_amount,
                    currency=offer.price_currency, latest_captured_at=captured_at, self_transfers=offer.self_transfers)
        it.fares.append(fare)
    elif fare.latest_price == offer.price_amount and fare.currency == offer.price_currency:
        fare.flexibility, fare.booking_url, fare.self_transfers = (offer.flexibility, offer.booking_url,
                                                          offer.self_transfers)
        fare.travel_class = offer.travel_class
        return result
    if captured_at >= fare.latest_captured_at:
        pinned_drop = (drops is not None and it.pinned and not it.hidden and old is not None
                       and offer.price_currency == fare.currency and offer.price_amount < fare.latest_price)
        target = drops is not None and not it.hidden and _crosses_target(session, trip_id, old, offer)
        if pinned_drop or target:
            drops.append(PriceDrop(trip_id=trip_id, fare_name=fare.fare_name, source=source,
                                   currency=offer.price_currency, new_price=offer.price_amount, target=target,
                                   old_price=old[0] if old is not None and old[1] == offer.price_currency else None))
        if offer.price_currency != fare.currency:
            fare.seen_price = None  # a drop in another currency is not a drop (#355)
        fare.latest_price, fare.currency, fare.latest_captured_at = (offer.price_amount, offer.price_currency,
                                                                      captured_at)
    fare.flexibility, fare.booking_url, fare.self_transfers = (offer.flexibility, offer.booking_url,
                                                          offer.self_transfers)
    fare.travel_class = offer.travel_class
    fare.prices.append(FarePrice(price=offer.price_amount, currency=offer.price_currency, captured_at=captured_at,
                                 capture_id=capture_id))
    session.flush()
    return "created" if result == "created" else "updated"


def upsert_offers(session: Session, trip_id: int, capture_id: int | None, offers: list[OfferIn], *, source: str,
                  captured_at: datetime, drops: list | None = None) -> dict[str, int]:
    """Upsert the offers, one transaction per offer: one failure does not roll back the others. An itinerary is
    matched by (trip, fingerprint), a fare by (itinerary, source, fare name). A new fare or a changed price adds one
    price row; the same price adds none. A race on the unique constraint is retried once. With a `drops` list, the
    lower prices of pinned fares are added to it (#512)."""
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for offer in offers:
        for attempt in (1, 2):
            pending: list | None = None if drops is None else []
            try:
                result = _upsert_one(session, trip_id, capture_id, offer, source, captured_at, pending)
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
                if drops is not None:
                    drops.extend(pending)
                break
    return counts


def capture_travelers(capture: Capture, parsed: int | None) -> int | None:
    """The traveler count of the parse, else the integer 1 to 9 of `search_context["travelers"]` (#764)."""
    ctx = capture.search_context_json
    return parsed if parsed is not None else count(ctx.get("travelers") if isinstance(ctx, dict) else None)


def parse_raw(body: IngestIn) -> tuple[list[OfferIn], list[dict], str | None, int | None]:
    """The offers and the rejected connections of the raw payload, by the parser of the source (none when the source
    has no parser). The third value is the reason when the parser cannot read the payload as a whole (P3): the
    capture is stored anyway, with the offers of the body. The fourth value is the traveler count (#764)."""
    parser = get_parser(body.source)
    if body.raw is None or parser is None:
        return [], [], None, None
    try:
        result = parser.parse(body.raw)
    except ValueError as e:
        return [], [], str(e)[:200], None
    return result.offers, result.errors, None, result.travelers


def set_result(capture: Capture, counts: dict, errors: list[dict], unreadable: str | None) -> None:
    """Keep the result of the last parse on the capture (#346): the counts, the first 50 errors (index and short
    reason only, P5) and the reason of an unreadable payload."""
    capture.offer_count = counts["created"] + counts["updated"] + counts["unchanged"]
    capture.rejected_count = len(errors)
    capture.errors_json = [{"index": e.get("index"), "reason": str(e.get("reason", ""))[:200]} for e in errors[:50]]
    capture.unreadable = unreadable


def reparse(session: Session, capture: Capture) -> dict | None:
    """Run the current parser of the source again on the stored raw of the capture (after a parser fix), and upsert
    its offers with the capture id and time. None when the capture has no raw or the source has no parser. Returns
    the counts as `store`, and "unreadable" (the reason, or None)."""
    raw, parser = load_raw(capture), get_parser(capture.source)
    if raw is None or parser is None:
        return None
    try:
        result = parser.parse(raw)
    except ValueError as e:
        log.warning("capture %s: reparse of %s raw payload failed: %s", capture.id, capture.source, e)
        counts = {"created": 0, "updated": 0, "unchanged": 0}
        set_result(capture, counts, [], str(e)[:200])
        capture.mismatch = None
        capture.travelers = capture_travelers(capture, None)
        session.commit()
        return {**counts, "rejected": 0, "unreadable": str(e)[:200]}
    counts = upsert_offers(session, capture.trip_id, capture.id, result.offers, source=capture.source,
                           captured_at=capture.captured_at)
    set_result(capture, counts, result.errors, None)
    capture.travelers = capture_travelers(capture, result.travelers)
    capture.mismatch = _trip_mismatch(session, capture.trip_id, result.offers, capture.travelers)
    session.commit()
    return {**counts, "rejected": len(result.errors), "unreadable": None}


def move_capture(session: Session, capture: Capture, target_trip_id: int) -> dict | None:
    """Move the offers of a capture into the wrong trip to the trip `target_trip_id` (#579, epic #578).

    The stored raw is parsed again into the target trip, as `reparse` does, because the price rows alone do not give
    all offers of a capture (an unchanged price adds no row). In the old trip, the price rows of the capture go, then
    each fare with no price row left, then each itinerary with no fare left; an offer that another capture of the
    old trip also has stays there (P5). A deleted itinerary gives its pin, booked mark, hidden mark and note to the
    itinerary of the same journey in the target trip. No price-drop message (not a new capture).

    One transaction: the offers go through `_upsert_one` with no commit per offer, so a failure (also a race with
    a parallel ingest) rolls back the whole move and leaves both trips as before. None when the capture has no raw
    or its source has no parser; {"unreadable": reason} when the parser cannot read the raw (nothing changes); else
    the counts of `reparse` and "removed" (the itineraries deleted from the old trip). `ValueError` when the target
    trip does not exist or is the trip of the capture."""
    old_trip_id = capture.trip_id
    if target_trip_id == old_trip_id:
        raise ValueError("the capture is already in this trip")
    if session.get(Trip, target_trip_id) is None:
        raise ValueError(f"no trip {target_trip_id}")
    raw, parser = load_raw(capture), get_parser(capture.source)
    if raw is None or parser is None:
        return None
    try:
        result = parser.parse(raw)
    except ValueError as e:
        return {"unreadable": str(e)[:200]}
    try:
        flags = _remove_from_old_trip(session, capture.id, old_trip_id)
        counts = {"created": 0, "updated": 0, "unchanged": 0}
        for offer in result.offers:
            counts[_upsert_one(session, target_trip_id, capture.id, offer, capture.source, capture.captured_at)] += 1
        _give_flags(session, target_trip_id, flags)
        capture.trip_id = target_trip_id
        set_result(capture, counts, result.errors, None)
        capture.travelers = capture_travelers(capture, result.travelers)
        capture.mismatch = _trip_mismatch(session, target_trip_id, result.offers, capture.travelers)
        session.commit()
    except Exception:
        session.rollback()
        raise
    log.info("capture %s: moved from trip %s to trip %s", capture.id, old_trip_id, target_trip_id)
    return {**counts, "rejected": len(result.errors), "unreadable": None, "removed": len(flags)}


def _remove_from_old_trip(session: Session, capture_id: int, trip_id: int) -> dict[str, tuple]:
    """Delete the price rows of the capture in the trip, then the fares with no price row and the itineraries with
    no fare. A fare that keeps rows gets its latest price from its newest row. Returns the flags (pinned, booked,
    hidden, note) of each deleted itinerary by its fingerprint. The caller commits."""
    rows = session.scalars(select(FarePrice).join(Fare).join(Itinerary)
                           .where(FarePrice.capture_id == capture_id, Itinerary.trip_id == trip_id)).all()
    fares = list({id(r.fare): r.fare for r in rows}.values())
    for r in rows:
        r.fare.prices.remove(r)  # delete-orphan: the row is deleted at the flush
    itineraries = list({id(f.itinerary): f.itinerary for f in fares}.values())
    for fare in fares:
        if fare.prices:
            newest = max(fare.prices, key=lambda p: (p.captured_at, p.id))
            fare.latest_price, fare.currency, fare.latest_captured_at = newest.price, newest.currency, newest.captured_at
        else:
            fare.itinerary.fares.remove(fare)
    flags = {}
    for it in itineraries:
        if not it.fares:
            flags[it.fingerprint] = (it.pinned, it.booked, it.hidden, it.note)
            session.delete(it)
    session.flush()
    return flags


def _give_flags(session: Session, trip_id: int, flags: dict[str, tuple]) -> None:
    """Give the flags of the deleted itineraries (`_remove_from_old_trip`) to the same journeys in the trip. A flag
    that is on stays on, and a note of the target is kept."""
    if not flags:
        return
    for it in session.scalars(select(Itinerary).where(Itinerary.trip_id == trip_id,
                                                      Itinerary.fingerprint.in_(flags))):
        pinned, booked, hidden, note = flags[it.fingerprint]
        it.pinned, it.booked, it.hidden = it.pinned or pinned, it.booked or booked, it.hidden or hidden
        it.note = it.note or note
    session.flush()


def store(session: Session, body: IngestIn, drops: list | None = None) -> dict:
    """Store the capture of the body (with its raw, if any), then its valid offers; each price row links to the
    capture. The offers of a raw payload come from its parser (`app/parsers`); one bad connection is an entry of
    the errors and the others are stored. Returns {"created", "updated", "unchanged", "rejected", "errors", "warning", "trip_id", "trip_title"}: the
    errors are the offers that the schema or the parser rejected, with their index (#54). Each failure is logged
    with the capture id (P3)."""
    raw_offers, raw_errors, unreadable, travelers = parse_raw(body)
    trip_id = _choose_trip(session, body, list(body.offers) + raw_offers)
    capture = store_capture(session, trip_id, body)
    session.commit()
    if unreadable is not None:
        log.warning("capture %s: %s raw payload not read: %s", capture.id, body.source, unreadable)
    offers = list(body.offers) + raw_offers
    errors = list(body.offer_errors) + raw_errors
    for err in errors:
        log.warning("capture %s: %s %s rejected at index %s: %s", capture.id, body.source,
                    body.parser_version or "-", err.get("index"), err.get("reason"))
    counts = upsert_offers(session, trip_id, capture.id, offers, source=body.source,
                           captured_at=body.captured_at, drops=drops)
    set_result(capture, counts, errors, unreadable)
    capture.travelers = capture_travelers(capture, travelers)
    reason = _trip_mismatch(session, trip_id, offers, capture.travelers)
    capture.mismatch = reason
    # #720: an auto_trip capture that no trip matches suggests a new trip from its offers
    suggestion = suggest_trip(offers) if getattr(body, "auto_trip", False) and reason is not None else None
    delete_old_captures(session, retention_days(session), datetime.now(UTC))
    session.commit()
    trip = session.get(Trip, trip_id)
    warning = _warning_text(reason, capture.travelers, None if trip is None else trip.travelers)
    return {**counts, "rejected": len(errors), "errors": errors, "warning": warning,
            "trip_id": trip_id, "trip_title": None if trip is None else trip.title, "suggestion": suggestion}


def _choose_trip(session: Session, body: IngestIn, offers: list[OfferIn]) -> int:
    """The trip_id of the body; with `auto_trip`, the trip of tripmatch.best_trip (#719)."""
    selected = session.get(Trip, body.trip_id)
    if not getattr(body, "auto_trip", False) or selected is None:
        return body.trip_id
    planning = list(session.scalars(select(Trip).where(Trip.status == "planning")))
    return best_trip(planning, offers, selected).id


def _trip_mismatch(session: Session, trip_id: int, offers: list[OfferIn], travelers: int | None = None) -> str | None:
    """The reason of #555 (tripmatch.mismatch), or None. Stored on the capture (#556)."""
    trip = session.get(Trip, trip_id)
    return None if trip is None else mismatch(trip, offers, travelers)


def _warning_text(reason: str | None, travelers: int | None = None, trip_travelers: int | None = None) -> str | None:
    """The warning of #555: the offers do not match the places or the date of the trip (#765: or its travelers).
    The data is stored anyway."""
    if reason is None:
        return None
    if reason == "travelers":
        return travelers_text(travelers, trip_travelers)
    return f"These offers do not match the trip ({reason})"
