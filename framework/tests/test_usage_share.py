"""framework/tools/usage.py: the projects of one account share its week. Each pacer plans with its part of the 7-day
budget (`week_share`) and leaves a reserve to the sessions of the owner (`week_reserve`) until the last hours."""
import math

import usage

NOW = 1_800_000_000
H = 3600
ALONE = {"share7": 1.0, "reserve7": 0.0}     # the project has the account alone, and the owner has no reserve


def five(used=0.3):
    return {"five_hour": (used, NOW + 2 * H, "allowed")}


def week(used, hours_left):
    return five() | {"seven_day": (used, NOW + hours_left * H, "allowed")}


def before(used, left, burn7, n=11):
    """The rule before the share and the reserve (#1695), for the 5-hour count 11 of `five()`."""
    elapsed = 1 - left / 168
    if burn7 and used > elapsed:
        return min(n, math.floor(max(1 - used, 0) / max(left, 0.25) / burn7))
    return n // 2 if used > elapsed + 0.10 else n


def test_the_whole_share_and_no_reserve_change_nothing():
    for used, left in ((0.52, 145), (0.3, 134), (0.2, 96), (0.95, 6), (0.5, 100)):
        for burn7 in (None, 0.001, 0.0053):
            assert usage.target_runs(week(used, left), NOW, burn7=burn7, free7=0, week=True, hi=99, **ALONE) == \
                before(used, left, burn7), (used, left, burn7)


def test_a_week_ahead_gives_each_project_its_share_of_the_budget():
    u = week(0.3, 134)                                                   # 30 % used after 20 % of the week
    alone = usage.target_runs(u, NOW, burn7=0.001, free7=0, week=True, hi=99, **ALONE)
    assert alone == 5                                                    # 0.7 / 134 h / 0.001 = 5.2 runs
    parts = [usage.target_runs(u, NOW, burn7=0.001, free7=0, week=True, hi=99, share7=s, reserve7=0.0) for s in (0.4, 0.4, 0.2)]
    assert parts == [2, 2, 1] and sum(parts) <= alone                    # together not more than the account carries
    assert usage.target_runs(u, NOW, burn7=0.005, free7=0, week=True, hi=99, share7=0.25, reserve7=0.0) == 0   # a part of one run: wait


def test_a_week_behind_the_pace_has_no_limit_from_the_share():
    u = week(0.2, 96)                                                    # 20 % used after 43 % of the week
    free = usage.target_runs(five(), NOW, hi=99)
    assert usage.target_runs(u, NOW, burn7=0.005, free7=0, week=True, hi=99, share7=0.1, reserve7=0.0) == free


def test_the_reserve_lowers_the_pace_and_the_budget():
    u = week(0.40, 96)                                                   # 40 % used after 42.9 % of the week
    free = usage.target_runs(five(), NOW, hi=99)
    assert usage.target_runs(u, NOW, burn7=0.001, free7=0, week=True, hi=99, **ALONE) == free           # behind the pace
    n = usage.target_runs(u, NOW, burn7=0.001, free7=0, week=True, hi=99, share7=1.0, reserve7=0.10)       # the pace is 38.6 %
    assert n == 5 and n < free                                           # (0.9 - 0.4) / 96 h / 0.001 = 5.2 runs
    assert usage.target_runs(week(0.92, 40), NOW, burn7=0.001, free7=0, week=True, hi=99, share7=1.0, reserve7=0.10) == 0   # only the reserve is left


def test_the_reserve_is_free_again_in_the_last_hours():
    late = week(0.92, usage.RELEASE7 - 2)                                # 10 h before the reset: the pace is 94 %
    assert usage.target_runs(late, NOW, burn7=0.001, free7=0, week=True, hi=99, share7=1.0, reserve7=0.10) == \
        usage.target_runs(five(), NOW, hi=99)
    ahead = week(0.965, usage.RELEASE7 - 2)                              # ahead of the pace: (1 - 0.965) / 10 h / 0.001 = 3.5 runs
    assert usage.target_runs(ahead, NOW, burn7=0.001, free7=0, week=True, hi=99, share7=1.0, reserve7=0.10) == 3


def test_the_settings_come_from_the_pacing_table():
    pacing = usage.CONFIG.get("pacing", {})
    assert usage.SHARE7 == pacing.get("week_share", 1.0) and usage.RESERVE7 == pacing.get("week_reserve", 0.0)
    assert 0 < usage.SHARE7 <= 1 and 0 <= usage.RESERVE7 < 1
