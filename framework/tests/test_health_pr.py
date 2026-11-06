"""framework/tools/health.py counts the `pr #n` results of the Metrics lines by the PR state (#902)."""
import datetime

import health

SINCE = datetime.datetime(2026, 10, 25, 12, 0, tzinfo=datetime.timezone.utc)


def test_pr_results_by_the_pr_state():
    comments = [{"body": "Did #5.\nMetrics: ticket #5 · size:S · pr #11 · 30 min · setup 2 min · checks 1"},
                {"body": "Metrics: ticket #6 · size:M · pr #12 · 40 min · setup 0 min · checks 2\n"
                         "Metrics: ticket #7 · size:S · none · 9 min · setup 1 min · checks 0"},
                {"body": "Metrics: ticket #8 · size:S · pr #13 · 20 min · setup 1 min · checks 1"},
                {"body": "Text that names pr #14 · and no Metrics line"}]
    prs = [{"number": 11, "merged_at": "2026-10-25T13:00:00Z"}, {"number": 12, "merged_at": None}]
    assert health.pr_results(comments, prs) == ([11], [12, 13])
    text = health.report(SINCE, [], [], comments, [], prs, [])
    assert "Metrics lines with pr #n: merged 1, not merged 2 (#12, #13)" in text
    assert "merged 0, not merged 0" in health.report(SINCE, [], [], [], [], [], [])
