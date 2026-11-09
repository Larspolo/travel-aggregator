import base64

from app import totp

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode("ascii")


def test_rfc6238_vectors_sha1():
    # Last 6 digits of the 8-digit values of RFC 6238, Appendix B.
    assert totp.code(RFC_SECRET, 59) == "287082"
    assert totp.code(RFC_SECRET, 1111111109) == "081804"
    assert totp.code(RFC_SECRET, 1111111111) == "050471"
    assert totp.code(RFC_SECRET, 1234567890) == "005924"
    assert totp.code(RFC_SECRET, 2000000000) == "279037"


def test_check_accepts_neighbour_steps_and_rejects_others():
    now = 1111111111.0
    step = int(now) // 30
    before = totp.code(RFC_SECRET, now - 30)
    after = totp.code(RFC_SECRET, now + 30)
    two_away = totp.code(RFC_SECRET, now + 60)
    assert totp.check(RFC_SECRET, before, now, 0) == step - 1
    assert totp.check(RFC_SECRET, after, now, 0) == step + 1
    current = totp.code(RFC_SECRET, now)
    assert totp.check(RFC_SECRET, current, now, 0) == step
    assert totp.check(RFC_SECRET, two_away, now, 0) is None
    wrong = "000000" if current != "000000" else "111111"
    assert totp.check(RFC_SECRET, wrong, now, 0) is None


def test_check_rejects_used_step():
    now = 1111111111.0
    step = int(now) // 30
    current = totp.code(RFC_SECRET, now)
    assert totp.check(RFC_SECRET, current, now, step) is None
    assert totp.check(RFC_SECRET, current, now, step - 1) == step
    before = totp.code(RFC_SECRET, now - 30)
    assert totp.check(RFC_SECRET, before, now, step - 1) is None


def test_check_rejects_empty_and_letters():
    now = 1111111111.0
    assert totp.check(RFC_SECRET, "", now, 0) is None
    assert totp.check(RFC_SECRET, "28708a", now, 0) is None
    assert totp.check(RFC_SECRET, "abcdef", now, 0) is None


def test_check_accepts_space_inside_code():
    now = 59.0
    assert totp.check(RFC_SECRET, "287 082", now, 0) == 1


def test_new_secret_is_base32_and_random():
    first = totp.new_secret()
    second = totp.new_secret()
    assert len(first) == 32
    assert set(first) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
    assert "=" not in first
    assert first != second


def test_uri_text():
    assert totp.uri("ABCDEF") == (
        "otpauth://totp/travel-aggregator:owner?secret=ABCDEF"
        "&issuer=travel-aggregator&algorithm=SHA1&digits=6&period=30"
    )
