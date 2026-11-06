"""The database models (docs/SPEC.md section 6). Times are timestamptz; money is Numeric(10, 2)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint,
    func, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

Money = Numeric(10, 2)


def _tz() -> DateTime:
    return DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    origin_text: Mapped[str | None] = mapped_column(String(200))
    destination_text: Mapped[str | None] = mapped_column(String(200))
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    travelers: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(20), default="planning", server_default="planning")
    notes: Mapped[str | None] = mapped_column(Text)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("score_profiles.id", ondelete="SET NULL"))  # #232
    # The outbound trip of a return trip, and its return trip (#340): one-to-one.
    return_of_id: Mapped[int | None] = mapped_column(ForeignKey("trips.id", ondelete="SET NULL"), unique=True)
    created_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())

    itineraries: Mapped[list["Itinerary"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    return_of: Mapped["Trip | None"] = relationship(back_populates="return_trip", remote_side=[id],
                                                    foreign_keys=[return_of_id])
    return_trip: Mapped["Trip | None"] = relationship(back_populates="return_of", foreign_keys=[return_of_id],
                                                      remote_side=[return_of_id], uselist=False)


class Itinerary(Base):
    __tablename__ = "itineraries"
    __table_args__ = (UniqueConstraint("trip_id", "fingerprint", name="uq_itineraries_trip_fingerprint"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(128))
    mode_summary: Mapped[str | None] = mapped_column(String(100))
    depart_at: Mapped[datetime] = mapped_column(_tz())
    arrive_at: Mapped[datetime] = mapped_column(_tz())
    duration_min: Mapped[int] = mapped_column(Integer)
    transfers: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_seen_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    booked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    note: Mapped[str | None] = mapped_column(Text)

    trip: Mapped[Trip] = relationship(back_populates="itineraries")
    legs: Mapped[list["Leg"]] = relationship(back_populates="itinerary", cascade="all, delete-orphan", order_by="Leg.seq")
    fares: Mapped[list["Fare"]] = relationship(back_populates="itinerary", cascade="all, delete-orphan")


class Leg(Base):
    __tablename__ = "legs"
    __table_args__ = (UniqueConstraint("itinerary_id", "seq", name="uq_legs_itinerary_seq"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    itinerary_id: Mapped[int] = mapped_column(ForeignKey("itineraries.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(20))
    carrier: Mapped[str | None] = mapped_column(String(100))
    service_no: Mapped[str | None] = mapped_column(String(50))
    from_name: Mapped[str] = mapped_column(String(200))
    from_code: Mapped[str | None] = mapped_column(String(20))
    to_name: Mapped[str] = mapped_column(String(200))
    to_code: Mapped[str | None] = mapped_column(String(20))
    depart_at: Mapped[datetime] = mapped_column(_tz())
    depart_offset_min: Mapped[int] = mapped_column(Integer)
    arrive_at: Mapped[datetime] = mapped_column(_tz())
    arrive_offset_min: Mapped[int] = mapped_column(Integer)

    itinerary: Mapped[Itinerary] = relationship(back_populates="legs")


class Fare(Base):
    __tablename__ = "fares"

    id: Mapped[int] = mapped_column(primary_key=True)
    itinerary_id: Mapped[int] = mapped_column(ForeignKey("itineraries.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(50))
    fare_name: Mapped[str | None] = mapped_column(String(100))
    flexibility: Mapped[str | None] = mapped_column(String(50))
    self_transfers: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # #176, derived at ingest
    booking_url: Mapped[str | None] = mapped_column(Text)
    latest_price: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    latest_captured_at: Mapped[datetime] = mapped_column(_tz())

    itinerary: Mapped[Itinerary] = relationship(back_populates="fares")
    prices: Mapped[list["FarePrice"]] = relationship(back_populates="fare", cascade="all, delete-orphan")


class FarePrice(Base):
    __tablename__ = "fare_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    fare_id: Mapped[int] = mapped_column(ForeignKey("fares.id", ondelete="CASCADE"), index=True)
    price: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    captured_at: Mapped[datetime] = mapped_column(_tz())
    capture_id: Mapped[int | None] = mapped_column(ForeignKey("captures.id", ondelete="SET NULL"), index=True)

    fare: Mapped[Fare] = relationship(back_populates="prices")


class Capture(Base):
    """One ingest call. `raw_gz` is the gzip of the JSON of `raw` (NULL when the call had no raw), for a reparse.
    Privacy (P5): no request headers and no cookies."""
    __tablename__ = "captures"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(50))
    parser_version: Mapped[str | None] = mapped_column(String(50))
    page_url: Mapped[str | None] = mapped_column(String(2000))
    search_context_json: Mapped[dict | None] = mapped_column(JSON)
    raw_gz: Mapped[bytes | None] = mapped_column(LargeBinary)
    captured_at: Mapped[datetime] = mapped_column(_tz())
    # The result of the last parse (#346); NULL for the captures before 0010.
    offer_count: Mapped[int | None] = mapped_column(Integer)
    rejected_count: Mapped[int | None] = mapped_column(Integer)
    errors_json: Mapped[list | None] = mapped_column(JSON)
    unreadable: Mapped[str | None] = mapped_column(String(200))


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(_tz(), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(_tz())
    revoked_at: Mapped[datetime | None] = mapped_column(_tz())


class AccessTime(Base):
    """A way from a place to a station (`access`) or from a station to a place (`egress`), #97."""
    __tablename__ = "access_times"
    __table_args__ = (
        CheckConstraint("kind IN ('access', 'egress')", name="ck_access_times_kind"),
        CheckConstraint("minutes >= 0", name="ck_access_times_minutes"),
        CheckConstraint("cost >= 0", name="ck_access_times_cost"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    place_text: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(10))
    minutes: Mapped[int] = mapped_column(Integer)
    cost: Mapped[Decimal] = mapped_column(Money)


class ScoreProfile(Base):
    """A named set of weights (#229). Only one row can be the default: a partial unique index."""
    __tablename__ = "score_profiles"
    __table_args__ = (
        Index("uq_score_profiles_default", "is_default", unique=True, postgresql_where=text("is_default")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    config_json: Mapped[dict] = mapped_column(JSON)


class Setting(Base):
    """A value that the owner sets on the settings page (#207)."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
