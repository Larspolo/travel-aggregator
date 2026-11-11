"""framework/tools/health.py counts the re-run of a flake by a run (autopilot step 6.9) apart from the runs that the
owner started again (lever 9): on 2026-11-11, 2 of 2 "started again by hand" were pull_request runs on `claude/*`
branches (#2349)."""
import datetime

import health

T = datetime.datetime(2026, 11, 11, 8, tzinfo=datetime.timezone.utc)
iso = (T + datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(name="CI", event="pull_request", branch="claude/x", attempt=2):
    return {"name": name, "event": event, "head_branch": branch, "run_attempt": attempt, "status": "completed",
            "conclusion": "success", "run_started_at": iso, "created_at": iso, "updated_at": iso}


def test_a_flake_rerun_of_a_run_is_no_owner_work():
    runs = [run(), run(branch="agent/7-x"), run(branch="ccr-1"), run(attempt=1)]
    assert health.held_runs(runs) == ({}, {})
    assert health.run_reruns(runs) == {"CI": 3}


def test_other_reruns_stay_owner_work():
    runs = [run(name="Pacer", event="schedule", branch="main"), run(event="push", branch="main"),
            run(branch="feature/x")]
    assert health.held_runs(runs)[1] == {"CI": 2, "Pacer": 1}
    assert health.run_reruns(runs) == {}


def test_the_report_has_the_line():
    lines = health.report(T, [run(), run(name="Pacer", event="schedule", branch="main")], [], [], [], [], []).splitlines()
    assert "Runs held by GitHub (#4645): 0 · started again by hand: Pacer 1" in lines
    assert "CI re-runs of the runs (a flake, autopilot 6.9, #2349; no owner work): CI 1" in lines
