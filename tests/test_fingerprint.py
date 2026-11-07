"""Tests of the itinerary fingerprint (docs/SPEC.md section 5): a re-capture of the same itinerary is found again."""

import pytest

from app.ingest import fingerprint
from app.schemas import LegIn


def _leg(**overrides: object) -> LegIn:
    data: dict[str, object] = {
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
    data.update(overrides)
    return LegIn.model_validate(data)


def _itinerary() -> list[LegIn]:
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
        {"service_no": "ICE 78"},
        {"mode": "bus"},
        {"depart_at": "2026-12-20T07:35:00+01:00"},
        {"arrive_at": "2026-12-20T14:03:00+01:00"},
    ],
)
def test_service_mode_or_time_changes_fingerprint(override: dict[str, object]) -> None:
    assert fingerprint([_leg(**override)]) != fingerprint([_leg()])


def test_same_instant_with_other_offset_gives_same_fingerprint() -> None:
    assert fingerprint([_leg(depart_at="2026-12-20T07:34:00+01:00")]) == fingerprint(
        [_leg(depart_at="2026-12-20T06:34:00+00:00")]
    )


def test_place_names_do_not_change_fingerprint() -> None:
    assert fingerprint([_leg(from_name="Amsterdam Centraal (wrong)")]) == fingerprint([_leg()])


def test_carrier_times_between_and_service_form_do_not_change_fingerprint() -> None:
    """The journey key of #481: bahn.de and NS International give the same train in other forms."""
    legs = _itinerary()
    other = [_leg(carrier=None, service_no="ice77", arrive_at="2026-12-20T07:34:00+01:00"),
             _leg(mode="bus", carrier=None, service_no="FB12", depart_at="2026-12-20T07:34:00+01:00",
                  arrive_at="2026-12-20T17:30:00+01:00")]
    assert fingerprint(other) == fingerprint(legs)
