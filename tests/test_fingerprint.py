"""Tests of the itinerary fingerprint (SPEC section 5, ingest rules)."""

import pytest

from app.ingest import fingerprint


def _leg(**overrides: object) -> dict[str, object]:
    leg: dict[str, object] = {
        "mode": "train",
        "carrier": "DB",
        "service_no": "ICE 77",
        "from_name": "Amsterdam Centraal",
        "from_code": None,
        "to_name": "Basel SBB",
        "to_code": None,
        "depart_at": "2026-12-20T07:34:00+01:00",
        "arrive_at": "2026-12-20T14:02:00+01:00",
    }
    leg.update(overrides)
    return leg


def _itinerary() -> list[dict[str, object]]:
    return [
        _leg(),
        _leg(
            mode="bus",
            carrier="FlixBus",
            service_no="FB 12",
            depart_at="2026-12-20T15:00:00+01:00",
            arrive_at="2026-12-20T17:30:00+01:00",
        ),
    ]


def test_same_legs_give_same_fingerprint() -> None:
    assert fingerprint(_itinerary()) == fingerprint(_itinerary())


def test_fingerprint_is_hex_sha256() -> None:
    value = fingerprint(_itinerary())
    assert len(value) == 64
    int(value, 16)


def test_leg_order_changes_fingerprint() -> None:
    legs = _itinerary()
    assert fingerprint(legs) != fingerprint(list(reversed(legs)))


@pytest.mark.parametrize(
    "override",
    [
        {"carrier": "ÖBB"},
        {"service_no": "ICE 78"},
        {"mode": "bus"},
        {"depart_at": "2026-12-20T07:35:00+01:00"},
        {"arrive_at": "2026-12-20T14:03:00+01:00"},
    ],
)
def test_carrier_service_mode_or_time_changes_fingerprint(override: dict[str, object]) -> None:
    changed = [_leg(**override)]
    assert fingerprint(changed) != fingerprint([_leg()])


def test_same_instant_with_other_offset_gives_same_fingerprint() -> None:
    assert fingerprint([_leg(depart_at="2026-12-20T07:34:00+01:00")]) == fingerprint(
        [_leg(depart_at="2026-12-20T06:34:00+00:00")]
    )


def test_price_and_fare_name_do_not_change_fingerprint() -> None:
    offer_a = {"price_amount": "89.90", "fare_name": "Sparpreis", "legs": _itinerary()}
    offer_b = {"price_amount": "120.00", "fare_name": "Flexpreis", "legs": _itinerary()}
    assert fingerprint(offer_a["legs"]) == fingerprint(offer_b["legs"])


def test_place_names_do_not_change_fingerprint() -> None:
    assert fingerprint([_leg(from_name="Amsterdam Centraal (wrong)")]) == fingerprint([_leg()])


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError):
        fingerprint([_leg(depart_at="2026-12-20T07:34:00")])
