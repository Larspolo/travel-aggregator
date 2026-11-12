"""framework/tools/claim.py: a week quota that runs out before its reset gives the highest review floor (#2574).
Then a review costs a ticket later in the week also when few tickets are ready."""
import claim
import usage

DAY = 86400
NOW = 1_800_000_000


def week(used, days_left):
    return {"five_hour": (0.1, NOW + 3600, "allowed"), "seven_day": (used, NOW + days_left * DAY, "allowed")}


def test_the_week_binds_when_its_rate_uses_the_quota_before_the_reset():
    assert usage.week_binds(week(0.97, 1), NOW)            # 6 days gone: 0.03 lasts 4.5 hours
    assert not usage.week_binds(week(0.50, 1), NOW)        # 0.50 lasts 6 more days
    assert not usage.week_binds({"five_hour": (0.1, NOW, "allowed")}, NOW)   # no 7-day window
    assert not usage.week_binds(week(0.0, 3), NOW)         # no rate yet


def test_the_week_line_keeps_its_text():
    assert "runs out" in usage.week_line(week(0.97, 1), NOW)
    assert "lasts to the reset" in usage.week_line(week(0.50, 1), NOW)


def test_claim_reads_the_quota_and_a_failed_read_is_not_a_binding_week():
    assert claim.week_binds(lambda: week(0.97, 1), NOW)
    assert not claim.week_binds(lambda: week(0.30, 4), NOW)

    def broken():
        raise OSError("no CLI")

    assert not claim.week_binds(broken, NOW)


def test_a_binding_week_gives_the_highest_floor():
    assert claim.next_gap(claim.REVIEW_MIN, True, claim.REVIEW_MAX_MIN) == claim.REVIEW_MAX_MIN
