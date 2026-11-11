"""Read the schema.org reservations of a confirmation e-mail (#2296)."""

from decimal import Decimal
from pathlib import Path

import pytest

from app.booking_mail import read_booking
from app.schemas import MAX_MAIL_BYTES

FIX = Path(__file__).parent / "fixtures" / "booking_mail"


def load(name):
    return read_booking((FIX / name).read_bytes())


def test_train_two_legs_in_order():
    b = load("train.eml")
    assert (b.code, b.price, b.currency) == ("XYZ123", Decimal("89.90"), "EUR")
    assert [leg.origin for leg in b.legs] == ["Amsterdam Centraal", "Köln Hbf"]
    assert all(leg.mode == "train" and leg.depart_at.tzinfo and leg.arrive_at.tzinfo for leg in b.legs)
    assert b.legs[0].depart_at < b.legs[1].depart_at
    assert (b.legs[0].carrier, b.legs[0].number) == ("Example Rail", "ICE 123")


def test_flight():
    b = load("flight.eml")
    (leg,) = b.legs
    assert (leg.mode, leg.origin, leg.destination, leg.carrier, leg.number) == (
        "flight", "AMS", "Barcelona El Prat", "Example Air", "110")
    assert (b.code, b.price) == ("RXJ34P", Decimal("120"))


def test_bus():
    b = load("bus.eml")
    (leg,) = b.legs
    assert (leg.mode, leg.origin, leg.destination, leg.number) == ("bus", "Utrecht Jaarbeurs", "Berlin ZOB", "N1")
    assert b.price == Decimal("19.99")


def test_no_markup_gives_none():
    assert load("no_markup.eml") is None


def test_bad_json_and_naive_time_are_skipped():
    b = load("not_json.eml")
    assert len(b.legs) == 1 and b.legs[0].depart_at.utcoffset() is not None


def test_naive_time_only_gives_none():
    raw = (FIX / "bus.eml").read_bytes().replace(b"2027-05-03T22:00:00+02:00", b"2027-05-03T22:00:00")
    assert read_booking(raw) is None


def test_too_large_raises():
    with pytest.raises(ValueError):
        read_booking(b"x" * (MAX_MAIL_BYTES + 1))
