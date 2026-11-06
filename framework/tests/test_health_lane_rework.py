"""The rework rate of each lane in health.py (#5533)."""
from datetime import datetime, timezone

import health

SINCE = datetime(2026, 10, 30, tzinfo=timezone.utc)
REPORTS = [{"body": "Metrics: ticket #1 · x · pr #10 · 30 min · lane haiku"},
           {"body": "Metrics: ticket #2 · x · pr #20 · 40 min"},
           {"body": "Metrics: ticket #3 · x · pr #10 · 5 min · lane deep"}]
PRS = [{"number": 10, "merged_at": "2026-10-30T10:00:00Z"}, {"number": 20, "merged_at": "2026-10-30T11:00:00Z"}]
BUG = {"number": 30, "title": "Bug", "created_at": "2026-10-31T00:00:00Z", "body": "Broken by #20.", "labels": [{"name": "bug"}]}


def test_lane_rework():
    assert health.lane_rework([BUG], PRS, REPORTS, SINCE) == {"haiku": (0, 1), "opus": (1, 1)}


def test_total_is_rework():
    total = sum(b for b, _ in health.lane_rework([BUG], PRS, REPORTS, SINCE).values())
    assert total == health.weak_spots([BUG], [], PRS, [], SINCE)["rework"]
