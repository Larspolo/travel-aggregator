"""The manual offer form (#118): the owner types one offer with one to four legs, and the app stores it as an offer
of source `manual`. The Pydantic models of the ingest validate it (P4)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from decimal import Decimal

from pydantic import ValidationError, create_model
from sqlalchemy.orm import Session

from app import ingest
from app.auth import require_login, verify_csrf
from app.db import get_session
from app.models import Fare, FarePrice
from app.schemas import IngestIn, OfferIn
from app.web.pages import _get_trip, templates

router = APIRouter()

MAX_FORM_LEGS = 4
LEG_FIELDS = ("mode", "from_name", "to_name", "depart_at", "arrive_at")
MODES = ("train", "bus", "flight", "ferry", "car", "other")
CLASSES = (("", "Not set"), ("first", "1st class"), ("standard", "2nd class"))  # the value and the label (#740)


def _page(request: Request, trip_id: int, values: dict, errors: list[str], code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request, "manual_form.html",
                                      {"trip_id": trip_id, "values": values, "errors": errors,
                                       "legs": range(MAX_FORM_LEGS), "modes": MODES, "classes": CLASSES},
                                      status_code=code)


def _offer(values: dict) -> dict:
    """The form values as an OfferIn dict. A leg with no field filled in is left out."""
    offset = values["utc_offset"] or "+00:00"
    legs = []
    for i in range(MAX_FORM_LEGS):
        leg = {k: values[f"leg{i}_{k}"] for k in LEG_FIELDS}
        if not any(leg[k] for k in LEG_FIELDS if k != "mode"):
            continue
        for k in ("depart_at", "arrive_at"):
            leg[k] = f"{leg[k]}{offset}" if leg[k] else leg[k]  # a datetime-local value has no offset
        legs.append(leg)
    return {"price_amount": values["price_amount"], "price_currency": values["price_currency"] or "EUR",
            "fare_name": values["fare_name"] or None, "booking_url": values["booking_url"] or None,
            "travel_class": values["travel_class"] or None, "legs": legs}


@router.get("/trips/{trip_id}/offers/new", response_class=HTMLResponse, dependencies=[Depends(require_login)])
def manual_form(request: Request, trip_id: int, session: Session = Depends(get_session)) -> HTMLResponse:
    trip = _get_trip(session, trip_id)
    return _page(request, trip_id, {"price_currency": "EUR", "utc_offset": "+01:00",
                                    "travelers": str(trip.travelers or 1)}, [])


@router.post("/trips/{trip_id}/offers/new", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
async def manual_offer(request: Request, trip_id: int, session: Session = Depends(get_session)):
    _get_trip(session, trip_id)
    form = await request.form()
    names = ["price_amount", "price_currency", "fare_name", "booking_url", "travel_class", "utc_offset", "travelers"]
    names += [f"leg{i}_{k}" for i in range(MAX_FORM_LEGS) for k in LEG_FIELDS]
    values = {k: str(form.get(k, "")).strip() for k in names}
    errors = []
    travelers = int(values["travelers"]) if values["travelers"].isdigit() else None
    if values["travelers"] and (travelers is None or not 1 <= travelers <= 9):
        errors.append("travelers: the price is for 1 to 9 travelers")  # the count of the price (#1028)
    try:
        offer = OfferIn.model_validate(_offer(values))  # first: IngestIn keeps a bad offer only as a count
        body = IngestIn(trip_id=trip_id, source="manual", captured_at=datetime.now(timezone.utc), offers=[offer],
                        search_context={"travelers": travelers} if travelers else None)
    except ValidationError as e:
        errors += [f"{'.'.join(map(str, err['loc'])) or 'form'}: {err['msg']}"
                  for err in e.errors(include_input=False, include_url=False)]
        return _page(request, trip_id, values, errors, 422)
    if errors:
        return _page(request, trip_id, values, errors, 422)
    ingest.store(session, body)
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


def _manual_fare(session: Session, trip_id: int, fare_id: int, action: str = "deleted") -> Fare:
    """The fare of the trip, 404 when it is not in the trip and 400 when it is not a manual offer (#1252)."""
    _get_trip(session, trip_id)
    fare = session.get(Fare, fare_id)
    if fare is None or fare.itinerary.trip_id != trip_id:
        raise HTTPException(404, "Offer not found")
    if fare.source != "manual":
        raise HTTPException(400, f"Only a manual offer can be {action}")
    return fare


@router.get("/trips/{trip_id}/fares/{fare_id}/delete", response_class=HTMLResponse,
            dependencies=[Depends(require_login)])
def manual_delete_form(request: Request, trip_id: int, fare_id: int,
                       session: Session = Depends(get_session)) -> HTMLResponse:
    fare = _manual_fare(session, trip_id, fare_id)
    return templates.TemplateResponse(request, "manual_delete.html",
                                      {"trip_id": trip_id, "fare": fare, "it": fare.itinerary})


@router.post("/trips/{trip_id}/fares/{fare_id}/delete",
             dependencies=[Depends(require_login), Depends(verify_csrf)])
def manual_delete(trip_id: int, fare_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    # The fare cascade deletes its prices; the capture stays. An itinerary with no fare left goes too (its legs cascade).
    fare = _manual_fare(session, trip_id, fare_id)
    it = fare.itinerary
    it.fares.remove(fare)
    session.flush()
    if not it.fares:
        session.delete(it)
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)


# The price rules of OfferIn, with no legs (#1253, P4).
PriceIn = create_model("PriceIn", price_amount=(Decimal, OfferIn.model_fields["price_amount"]),
                       price_currency=(str, OfferIn.model_fields["price_currency"]))


def _price_page(request: Request, trip_id: int, fare: Fare, values: dict, errors: list[str],
                code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request, "manual_price.html",
                                      {"trip_id": trip_id, "fare": fare, "it": fare.itinerary, "values": values,
                                       "errors": errors}, status_code=code)


@router.get("/trips/{trip_id}/fares/{fare_id}/price", response_class=HTMLResponse,
            dependencies=[Depends(require_login)])
def manual_price_form(request: Request, trip_id: int, fare_id: int,
                      session: Session = Depends(get_session)) -> HTMLResponse:
    fare = _manual_fare(session, trip_id, fare_id, "changed")
    return _price_page(request, trip_id, fare,
                       {"price_amount": str(fare.latest_price), "price_currency": fare.currency}, [])


@router.post("/trips/{trip_id}/fares/{fare_id}/price", response_class=HTMLResponse,
             dependencies=[Depends(require_login), Depends(verify_csrf)])
async def manual_price(request: Request, trip_id: int, fare_id: int, session: Session = Depends(get_session)):
    fare = _manual_fare(session, trip_id, fare_id, "changed")
    form = await request.form()
    values = {k: str(form.get(k, "")).strip() for k in ("price_amount", "price_currency")}
    try:
        price = PriceIn.model_validate({"price_amount": values["price_amount"],
                                        "price_currency": values["price_currency"].upper() or "EUR"})
    except ValidationError as e:
        errors = [f"{'.'.join(map(str, err['loc'])) or 'form'}: {err['msg']}"
                  for err in e.errors(include_input=False, include_url=False)]
        return _price_page(request, trip_id, fare, values, errors, 422)
    now = datetime.now(timezone.utc)
    session.add(FarePrice(fare_id=fare.id, price=price.price_amount, currency=price.price_currency,
                          captured_at=now, capture_id=None))
    fare.latest_price, fare.currency, fare.latest_captured_at = price.price_amount, price.price_currency, now
    session.commit()
    return RedirectResponse(f"/trips/{trip_id}", status_code=303)
