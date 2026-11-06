"""`dashboard.py --next` skips the tickets that a run holds: their claim fails, and the run read them for nothing."""
import datetime

import dashboard

NOW = datetime.datetime(2026, 10, 28, 12, 0, tzinfo=datetime.timezone.utc)
T = int(NOW.timestamp())


def test_a_beating_claim_holds_its_ticket():
    lines = [f"7 {T - 60} Claim #7", f"8 {T - 3600} Claim #8",                 # 8: no beat for an hour (stale)
             f"9 {T - 60} Release #9", f"10 {T - 3000} Claim #10", f"10-2 {T - 60} Beat #10",
             f"review-50pr-x {T} lock", "garbage"]
    assert dashboard.claimed(lines, NOW) == {7, 10}
