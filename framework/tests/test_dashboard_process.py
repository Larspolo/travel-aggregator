"""The dashboard counts the merged PRs with the label `process` of the last 24 hours (#901)."""
import datetime

import dashboard

NOW = datetime.datetime(2026, 10, 26, 14, 0, tzinfo=datetime.timezone.utc)


def pr(n, merged, *names):
    return {"number": n, "merged_at": merged, "labels": [{"name": k} for k in names], "body": ""}


def test_process_changes_counts_merged_process_prs_of_the_last_day():
    prs = [pr(1, "2026-10-26T13:00:00Z", "process"), pr(2, "2026-10-25T15:00:00Z", "process", "tooling"),
           pr(3, "2026-10-25T13:00:00Z", "process"), pr(4, None, "process"), pr(5, "2026-10-26T13:30:00Z")]
    assert dashboard.process_changes(prs, NOW) == 2
    body = dashboard.render("", [], {}, [], [], prs, NOW)
    assert "Process changes (24 h): 2 merged PRs with the label `process`" in body
    assert dashboard.render(body, [], {}, [], [], prs, NOW).count("Process changes (24 h)") == 1

