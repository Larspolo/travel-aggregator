"""framework/tools/usage.py reads the quota usage and sets the number of runs (owner request, 2026-10-26)."""
import json

import usage

NOW = 1_800_000_000
EVENT = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "unifiedWindows": {
    "five_hour": {"utilization": 0.3, "resetsAt": NOW + 2 * 3600, "status": "allowed"},
    "seven_day": {"utilization": 0.3, "resetsAt": NOW + 4 * 86400, "status": "allowed"}}}}


def test_parse_reads_the_windows():
    lines = ["not json", json.dumps({"type": "system"}), json.dumps(EVENT), json.dumps({"type": "result"})]
    u = usage.parse(lines)
    assert u["five_hour"] == (0.3, NOW + 7200, "allowed") and u["seven_day"][0] == 0.3
    assert usage.parse(["{}"]) == {}


def test_target_fills_the_window():
    u = usage.parse([json.dumps(EVENT)])
    assert usage.target_runs(u, NOW, hi=99) == round((usage.END - 0.3) / 2 / usage.BURN)   # the last 2 hours: 11 runs


def test_target_slows_down_when_ahead_and_speeds_up_near_the_reset():
    early = {"five_hour": (0.85, NOW + 4 * 3600, "allowed")}                   # ahead of 90 % at 2 hours before the reset
    late = {"five_hour": (0.6, NOW + 900, "allowed")}
    assert usage.target_runs(early, NOW) == 1
    assert usage.target_runs(late, NOW) == usage.HI
    assert usage.target_runs({"five_hour": (0.97, NOW + 3600, "allowed")}, NOW) == usage.LO


def test_target_guards_the_week_and_stops_at_the_limit():
    fast_week = {"five_hour": (0.3, NOW + 7200, "allowed"), "seven_day": (0.8, NOW + 5 * 86400, "allowed")}
    assert usage.target_runs(fast_week, NOW, week=True, free7=0, hi=99) == 5         # half of 11: 80 % used after 2 of 7 days
    assert usage.target_runs({"five_hour": (1.0, NOW + 600, "rejected")}, NOW) == 0
    assert usage.target_runs({}, NOW) is None
