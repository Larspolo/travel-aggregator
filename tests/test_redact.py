import copy

from app.redact import PERSONAL_KEYS, REDACTED, redact


def test_traveler_values():
    raw = {"travelers": [{"firstName": "Ann", "last_name": "Lee", "DATE-OF-BIRTH": "1990-01-02"}],
           "price": 49.5}
    out = redact(raw, PERSONAL_KEYS, frozenset())
    assert out == {"travelers": [{"firstName": REDACTED, "last_name": REDACTED,
                                  "DATE-OF-BIRTH": REDACTED}], "price": 49.5}


def test_url_query():
    raw = {"u": "https://x.example/s?from=8000105&to=8000261&email=a@b.nl"}
    out = redact(raw, PERSONAL_KEYS, frozenset({"from", "to"}))
    assert out["u"] == "https://x.example/s?from=8000105&to=8000261&email=REDACTED"


def test_email_text_and_scalars_and_input_unchanged():
    raw = {"note": "mail me at ann@lee.nl please", "n": 3, "b": True, "z": None, "s": "Utrecht"}
    before = copy.deepcopy(raw)
    out = redact(raw, PERSONAL_KEYS, frozenset())
    assert out == {"note": REDACTED, "n": 3, "b": True, "z": None, "s": "Utrecht"}
    assert raw == before


def test_deep_payload():
    raw = node = {}
    for _ in range(5000):
        node["a"] = [{}]
        node = node["a"][0]
    node["email"] = "x"
    out = redact(raw, PERSONAL_KEYS, frozenset())
    for _ in range(5000):
        out = out["a"][0]
    assert out == {"email": REDACTED}
