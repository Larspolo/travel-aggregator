"""Two runs on one ticket: the claim names the run that was first, and a run whose ticket was taken over stops at its
next beat (owner, 2026-10-28). Only a won claim writes `in-progress` and "Started by" (#288, #1749)."""
import os
import subprocess
import sys
import time

import claim
import dashboard
from test_claim import TOOL, clones, tool  # noqa: F401  (clones is a fixture)


def test_the_second_run_learns_which_run_was_first(clones):  # noqa: F811
    a, b, _ = clones
    assert tool(a, "11").stdout.strip() == "claimed claim/11"
    r = tool(b, "11")
    assert r.returncode == 1
    assert "`run-0` (its last claim 0 min ago) was first" in r.stdout and "do not comment" in r.stdout


def test_a_run_whose_ticket_was_taken_over_stops_at_its_beat(clones):  # noqa: F811
    a, b, _ = clones
    env = dict(os.environ, GIT_COMMITTER_DATE=f"{int(time.time()) - 31 * 60} +0000")     # a beat 31 minutes ago
    assert subprocess.run([sys.executable, TOOL, "12"], cwd=a, env=env).returncode == 0
    assert tool(b, "12", "--takeover").stdout.strip() == "claimed claim/12-2"
    for flag in ("--beat", "--guard"):
        r = tool(a, "12", flag)
        assert r.returncode == 1 and "`run-1` took #12 over" in r.stderr and "Stop the work on #12 now" in r.stderr


def test_a_won_claim_writes_the_label_and_the_comment(monkeypatch):
    calls = []
    monkeypatch.setattr(dashboard, "api", lambda path, method="GET", data=None: calls.append((path, method, data)))
    monkeypatch.setattr(claim, "who", lambda: "claude/x-1")
    claim.start(7)
    assert calls[0] == ("issues/7/labels", "POST", {"labels": ["in-progress"]})
    assert calls[1][:2] == ("issues/7/comments", "POST")
    assert calls[1][2]["body"].startswith("Started by `claude/x-1`.") and dashboard.FOOTER in calls[1][2]["body"]
    assert claim.started_by_other([{"body": calls[1][2]["body"], "created_at": "2026-10-28T12:00:00Z"}], "claude/y",
                                  claim.datetime.datetime(2026, 10, 28, 12, 5, tzinfo=claim.datetime.timezone.utc).timestamp()) == "claude/x-1"
