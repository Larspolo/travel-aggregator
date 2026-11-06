"""framework/tools/cycle_start.py starts the Automerge sweep only when every check of the head is finished (#606)."""
import datetime

import cycle_start as start

NOW = datetime.datetime(2026, 11, 2, 12, 0, tzinfo=datetime.timezone.utc)


def pr(body="Closes #7", ref="claude/x-1", minutes=30):
    created = (NOW - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"number": 70, "head": {"ref": ref}, "body": body, "created_at": created, "labels": []}


ISSUES = {7: {"number": 7, "labels": [{"name": "in-progress"}]}}


def test_a_green_quick_with_browser_still_running_waits_for_ci():
    checks = [("quick", "completed", "success"), ("browser", "in_progress", None)]
    assert start.pr_work(pr(), ISSUES, checks, None, NOW) is None


def test_all_checks_finished_and_green_starts_the_sweep():
    checks = [("quick", "completed", "success"), ("browser", "completed", "success")]
    assert "Automerge sweep" in start.pr_work(pr(), ISSUES, checks, None, NOW)
