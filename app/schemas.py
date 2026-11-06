"""The body of POST /api/ingest (docs/SPEC.md section 5). Captured data is untrusted: Pydantic validates each field
and limits each size (P4, P5)."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

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
    legs: list[LegIn] = Field(min_length=1, max_length=MAX_LEGS)
    booking_url: str | None = Field(None, max_length=2000, pattern=r"^https?://")

    @model_validator(mode="after")
    def _legs_in_order(self) -> "OfferIn":
        for a, b in zip(self.legs, self.legs[1:]):
            if b.depart_at < a.arrive_at:
                raise ValueError("a leg departs before the leg before it arrives")
        return self


class IngestIn(BaseModel):
    trip_id: int = Field(gt=0)
    source: str = Field(min_length=1, max_length=50)
    parser_version: str | None = Field(None, max_length=50)
    captured_at: AwareDatetime
    page_url: str | None = Field(None, max_length=2000, pattern=r"^https?://")
    search_context: dict[str, Any] | None = None
    raw: Any = None
    offers: list[OfferIn] = Field(default_factory=list, max_length=MAX_OFFERS)

    @model_validator(mode="after")
    def _raw_or_offers(self) -> "IngestIn":
        if self.raw is None and not self.offers:
            raise ValueError("the body needs raw or offers")
        return self


def utc_offset_min(t: datetime) -> int:
    return int(t.utcoffset().total_seconds() // 60)
