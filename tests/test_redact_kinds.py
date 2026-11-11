from app.redact import PERSONAL_KEYS, REDACTED, redact


def test_phone_booking_and_card_values_are_redacted():
    raw = {
        "contact": {"phoneNumber": "+31 6 12345678", "mobile": "0612345678"},
        "booking": {"bookingCode": "AB12CD", "pnr": "XYZ789"},
        "payment": {"cardNumber": "4111111111111111"},
        "offers": [
            {"bookingReference": "QQ55RR", "cardNumber": "5500000000000004"},
            {"price": 19.9, "station": "Utrecht Centraal"},
        ],
    }
    out = redact(raw, PERSONAL_KEYS, frozenset())
    assert out == {
        "contact": {"phoneNumber": REDACTED, "mobile": REDACTED},
        "booking": {"bookingCode": REDACTED, "pnr": REDACTED},
        "payment": {"cardNumber": REDACTED},
        "offers": [
            {"bookingReference": REDACTED, "cardNumber": REDACTED},
            {"price": 19.9, "station": "Utrecht Centraal"},
        ],
    }


def test_personal_values_in_a_list_are_redacted():
    raw = {"values": [{"phoneNumber": "0612345678"}, {"pnr": "XYZ789"}, "Amsterdam"]}
    out = redact(raw, PERSONAL_KEYS, frozenset())
    assert out == {"values": [{"phoneNumber": REDACTED}, {"pnr": REDACTED}, "Amsterdam"]}
