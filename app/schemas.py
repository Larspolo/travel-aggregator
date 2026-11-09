"""The body of POST /api/ingest (docs/SPEC.md section 5). Captured data is untrusted: Pydantic validates each field
and limits each size (P4, P5)."""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

MAX_OFFERS = 500           # offers per batch
MAX_LEGS = 20              # legs per offer
MAX_BODY_BYTES = 5_000_000  # the whole request body, also the raw payload

Mode = Literal["train", "bus", "flight", "ferry", "car", "other"]


class LegIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    mode: Mode
    carrier: str | None = Field(None, max_length=100)
    service_no: str | None = Field(None, max_length=50)
    from_name: str = Field(min_length=1, max_length=200)
    from_code: str | None = Field(None, max_length=20)
    to_name: str = Field(min_length=1, max_length=200)
    to_code: str | None = Field(None, max_length=20)
    depart_at: AwareDatetime
    arrive_at: AwareDatetime
    # The ticket of the leg in a self-transfer offer (#176): a change of the number between two legs is a
    # self-transfer. A leg with no number is on the ticket of the leg before it.
    ticket: int | None = Field(None, ge=1, le=MAX_LEGS)

    @model_validator(mode="after")
    def _arrives_after_departure(self) -> "LegIn":
        if self.arrive_at < self.depart_at:
            raise ValueError("arrive_at is before depart_at")
        return self


class OfferIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    external_id: str | None = Field(None, max_length=200)
    price_amount: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    price_currency: str = Field(pattern=r"^[A-Z]{3}$")
    fare_name: str | None = Field(None, max_length=100)
    flexibility: str | None = Field(None, max_length=50)
    travel_class: Literal["first", "standard"] | None = None
    checked_bags_included: int | None = Field(None, ge=0, le=9)  # #1525
    checked_bag_price: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)  # first bag, price currency
    legs: list[LegIn] = Field(min_length=1, max_length=MAX_LEGS)
    booking_url: str | None = Field(None, max_length=2000, pattern=r"^https?://")

    @model_validator(mode="after")
    def _legs_in_order(self) -> "OfferIn":
        for a, b in zip(self.legs, self.legs[1:]):
            if b.depart_at < a.arrive_at:
                raise ValueError("a leg departs before the leg before it arrives")
        return self

    @property
    def self_transfers(self) -> int:
        """The count of transfers between two tickets (#176). The ingest stores it on the fare: the same journey can
        be one ticket at one source and two tickets at another."""
        count, current = 0, self.legs[0].ticket
        for leg in self.legs[1:]:
            if leg.ticket is not None and current is not None and leg.ticket != current:
                count += 1
            current = leg.ticket if leg.ticket is not None else current
        return count


class IngestIn(BaseModel):
    trip_id: int = Field(gt=0)
    # True: the server stores the offers into the planning trip that matches them, if trip_id does not (#719).
    auto_trip: bool = False
    source: str = Field(min_length=1, max_length=50)
    parser_version: str | None = Field(None, max_length=50)
    captured_at: AwareDatetime
    page_url: str | None = Field(None, max_length=2000, pattern=r"^https?://")
    search_context: dict[str, Any] | None = None
    raw: Any = None
    offers: list[OfferIn] = Field(default_factory=list, max_length=MAX_OFFERS)
    # One entry {"index", "reason"} per rejected offer (#54). Set only by `_split_offers`, never by the client.
    offer_errors: list[dict[str, Any]] = Field(default_factory=list, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _split_offers(cls, data: Any) -> Any:
        """Validate each offer on its own: a bad offer is rejected, the other offers stay (docs/SPEC.md section 5).
        A list that is not a list or is too long stays for the field check (422 for the envelope)."""
        if not isinstance(data, dict):
            return data
        data = {**data, "offer_errors": []}
        offers = data.get("offers")
        if not isinstance(offers, list) or len(offers) > MAX_OFFERS:
            return data
        good = []
        for i, raw in enumerate(offers):
            if isinstance(raw, OfferIn):
                good.append(raw)
                continue
            try:
                good.append(OfferIn.model_validate(raw))
            except ValidationError as e:
                data["offer_errors"].append({"index": i, "reason": _short_reason(e)})
        data["offers"] = good
        return data

    @model_validator(mode="after")
    def _raw_or_offers(self) -> "IngestIn":
        if self.raw is None and not self.offers and not self.offer_errors:
            raise ValueError("the body needs raw or offers")
        return self


def _short_reason(e: ValidationError) -> str:
    """The location and message of the first error, with no input value: the offer is untrusted (P5)."""
    err = e.errors(include_input=False, include_url=False)[0]
    loc = ".".join(str(x) for x in err["loc"])
    return f"{loc}: {err['msg']}"[:200] if loc else err["msg"][:200]


def utc_offset_min(t: datetime) -> int:
    return int(t.utcoffset().total_seconds() // 60)


TripStatus = Literal["planning", "booked", "archived"]


class TripForm(BaseModel):
    """The fields of the create and edit forms of a trip (#22). An empty text field is None."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    origin_text: str | None = Field(None, max_length=200)
    destination_text: str | None = Field(None, max_length=200)
    origin_alt_text: str | None = Field(None, max_length=200)  # other origins, comma-separated (#1422)
    destination_alt_text: str | None = Field(None, max_length=200)
    date_from: date | None = None
    date_to: date | None = None
    travelers: int = Field(1, ge=1, le=9)
    status: TripStatus = "planning"
    notes: str | None = Field(None, max_length=5000)
    target_price: Decimal | None = Field(None, gt=0, le=100000)  # EUR; the fares at or below it (#846)
    arrive_by: time | None = None  # the local time at the arrival place (#1294)
    profile_id: int | None = None  # the score profile of this trip; None = the default profile (#232)

    @model_validator(mode="before")
    @classmethod
    def _empty_is_none(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: (None if isinstance(v, str) and not v.strip() and k != "title" else v) for k, v in data.items()}
        return data

    @model_validator(mode="after")
    def _dates_in_order(self) -> "TripForm":
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("date_to is before date_from")
        return self
