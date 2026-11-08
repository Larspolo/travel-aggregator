"""The manual offer form (#118): the owner types one offer with one to four legs, and the app stores it as an offer
of source `manual`. The Pydantic models of the ingest validate it (P4)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import ingest
from app.auth import require_login, verify_csrf
from app.db import get_session
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
            "fare_name": values["fare_name"] or None, "travel_class": values["travel_class"] or None,
            "legs": legs}


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
    names = ["price_amount", "price_currency", "fare_name", "travel_class", "utc_offset", "travelers"]
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
