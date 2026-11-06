"""The closed roadmap epics per 1 % of the 7-day quota (#797)."""
import datetime

import health

T = lambda h: datetime.datetime(2026, 11, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(hours=h)
POINTS = [(T(0), 10.0, 80.0), (T(10), 12.0, 80.0), (T(20), 14.0, 81.0)]


def epic(n, hours, body="Roadmap: `site:x`", reason="completed", labels=("epic",)):
    return {"number": n, "closed_at": T(hours).isoformat(), "state_reason": reason, "body": body,
            "labels": [{"name": x} for x in labels]}


def test_counts_only_roadmap_epics_closed_as_done_in_the_period():
    issues = [epic(1, 5), epic(2, 15), epic(3, 5, reason="not_planned"), epic(4, 5, body="no key"),
              epic(5, 30), epic(6, 5, labels=("feature",)), dict(epic(7, 5), pull_request={})]
    assert health.features_per_week(issues, POINTS) == (0.5, 2, 4.0)


def test_none_with_too_few_points_or_no_quota():
    assert health.features_per_week([epic(1, 5)], POINTS[:1]) is None
    flat = [(T(0), 10.0, 80.0), (T(20), 10.0, 80.0)]
    assert health.features_per_week([epic(1, 5)], flat) is None
