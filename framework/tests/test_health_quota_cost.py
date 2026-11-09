"""health.py shows the rise of the 5-hour usage per $ of the run cost (#1577)."""
from datetime import datetime, timedelta, timezone

import health

T = datetime(2026, 11, 9, tzinfo=timezone.utc)
RESET = T + timedelta(hours=5)


def test_quota_per_dollar_divides_the_rise_by_the_cost():
    s = [(T, 0.10, RESET), (T + timedelta(hours=1), 0.30, RESET), (T + timedelta(hours=2), 0.50, RESET)]
    assert abs(health.quota_per_dollar(s, 20.0) - 0.02) < 1e-9
    assert abs(health.quota_per_merge(s, 4) - 0.10) < 1e-9


def test_a_new_window_adds_no_rise():
    s = [(T, 0.80, RESET), (T + timedelta(hours=1), 0.10, RESET + timedelta(hours=5))]
    assert health.quota_rise(s) == 0


def test_no_cost_or_no_rise_gives_none():
    s = [(T, 0.10, RESET), (T + timedelta(hours=1), 0.30, RESET)]
    assert health.quota_per_dollar(s, 0) is None
    assert health.quota_per_dollar(s[:1], 5.0) is None
