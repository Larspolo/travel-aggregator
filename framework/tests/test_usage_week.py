"""framework/tools/usage.py: a week used ahead of the time gets only the runs that its 7-day budget carries to the reset (#1695),
and the CLI line shows the weekly projection."""
import datetime

import health
import usage

NOW = 1_800_000_000
H = 3600


def five(used=0.3):
    return {"five_hour": (used, NOW + 2 * H, "allowed")}


def test_a_week_far_ahead_gets_the_runs_that_its_budget_carries_to_the_reset():
    u = five() | {"seven_day": (0.52, NOW + 145 * H, "allowed")}         # 52 % used after 23 h of 168 h
    n = usage.target_runs(u, NOW, burn7=0.0053, free7=0, week=True, hi=99)
    assert n == 0 and 0.52 + n * 145 * 0.0053 <= 1.0                     # one run would use 0.77: 129 % at the reset
    u = five() | {"seven_day": (0.3, NOW + 134 * H, "allowed")}          # 30 % after 20 % of the week
    n = usage.target_runs(u, NOW, burn7=0.001, free7=0, week=True, hi=99)
    assert n == 5 and 0.3 + n * 134 * 0.001 <= 1.0 < 0.3 + (n + 1) * 134 * 0.001
    assert usage.target_runs(u, NOW, burn7=0.0001, free7=0, week=True, hi=99) == \
        usage.target_runs(five(), NOW, hi=99) == 11                    # a large budget: no cap


def test_a_week_behind_the_time_keeps_the_count():
    u = five() | {"seven_day": (0.2, NOW + 4 * 86400, "allowed")}         # 20 % used after 43 % of the week
    assert usage.target_runs(u, NOW, burn7=0.05) == usage.target_runs(u, NOW) == usage.target_runs(five(), NOW)
    assert usage.target_runs(five() | {"seven_day": (0.9, NOW + H, "rejected")}, NOW, burn7=0.005, week=True) == 0


def test_the_line_shows_the_weekly_projection():
    u = five() | {"seven_day": (0.52, NOW + 145 * H, "allowed")}
    out = datetime.datetime.fromtimestamp(NOW + 0.48 / (0.52 / (23 * H)), datetime.timezone.utc)
    assert usage.week_line(u, NOW) == f"week ahead +38 pt · runs out {out:%a %H:%M}"
    assert usage.week_line(five() | {"seven_day": (0.1, NOW + 100 * H, "allowed")}, NOW) == \
        "week ahead -30 pt · lasts to the reset"
    assert usage.week_line(five(), NOW) == ""
    line = usage.describe(u, NOW, burn7=0.0053)
    assert "week ahead +38 pt · runs out" in line and "burn7 0.0053" in line
    assert line.endswith(f"target {usage.target_runs(u, NOW, burn7=0.0053)} runs")   # the pacing of agent.toml


def test_health_measures_the_weekly_burn_from_the_usage_lines():
    t = datetime.datetime(2026, 10, 27, 12, tzinfo=datetime.timezone.utc)
    line = lambda h, w: f"Usage: {t + datetime.timedelta(hours=h):%Y-%m-%dT%H:%M:%SZ} · usage 10.0% · resets " \
                        f"2026-10-27T17:30:00Z · runs 4 · week {w}% · release 80.0%"
    body = "\n".join(line(h / 2, 50 + h) for h in range(6))              # +1 point per half hour with 4 runs
    assert abs(health.weekly_burn([{"body": body}], t + datetime.timedelta(hours=3)) - 0.01 / 0.5 / 4) < 1e-9
    assert health.weekly_burn([{"body": "\n".join(line(h, 50) for h in range(3))}], t + datetime.timedelta(hours=3)) is None
