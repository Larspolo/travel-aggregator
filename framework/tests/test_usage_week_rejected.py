"""framework/tools/usage.py: a rejected 7-day window starts no run, also with no week guard (`week_guard = false`).
On 2026-11-12 the pacer started runs for 18 hours while the 7-day window was rejected: no run worked, and the
tickets that its briefs claimed (#2656, #2657, #2661) stayed stuck until the reset."""
import usage

NOW = 1_800_000_000
H = 3600


def test_a_rejected_week_gives_no_run_with_and_without_the_guard():
    u = {"five_hour": (0.0, NOW + 5 * H, "allowed"), "seven_day": (1.0, NOW + 11 * H, "rejected")}
    assert usage.target_runs(u, NOW, week=False) == 0
    assert usage.target_runs(u, NOW, week=True, burn7=0.005) == 0


def test_an_allowed_week_with_no_guard_keeps_the_count_of_the_five_hour_window():
    five = {"five_hour": (0.0, NOW + 5 * H, "allowed")}
    u = five | {"seven_day": (0.99, NOW + 11 * H, "allowed")}
    assert usage.target_runs(u, NOW, week=False) == usage.target_runs(five, NOW) > 0
