"""framework/tools/health.py counts the pull_request run of a github-actions[bot] push (Unconflict) as held: GitHub ends
it with 0 jobs (29 of 29 runs), so it is no red CI and no takeover cause "red CI" (#4988)."""
import datetime

import health

T = datetime.datetime(2026, 10, 31, 8, tzinfo=datetime.timezone.utc)
iso = lambda m: (T + datetime.timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ci(m, conclusion, actor, event="pull_request", branch="claude/x"):
    return {"name": "CI", "event": event, "actor": {"login": actor}, "status": "completed", "conclusion": conclusion,
            "run_started_at": iso(m), "created_at": iso(m), "updated_at": iso(m + 1), "head_branch": branch,
            "run_attempt": 1}


BOT, RUN = "github-actions[bot]", "Larspolo"


def test_a_bot_pull_request_run_is_held_and_not_red():
    runs = [ci(0, "failure", BOT), ci(1, "action_required", BOT), ci(2, "failure", RUN),
            ci(3, "success", BOT, event="workflow_dispatch"), ci(4, "failure", BOT, event="workflow_dispatch")]
    assert health.held_runs(runs)[0] == {"CI": 2}
    assert health.ci_runs(runs, T)["CI"][3] == 2           # the red run of a person and the red dispatch run


def comment(n, m, body):
    return {"issue_url": f"https://api.github.com/repos/o/r/issues/{n}", "created_at": iso(m), "body": body}


def test_a_held_run_gives_no_red_ci_takeover():
    comments = [comment(7, 0, "Started by `claude/x`."), comment(7, 30, "Taken over by `claude/y`.")]
    prs = [{"number": 8, "head": {"ref": "claude/x"}, "body": "Closes #7"}]
    held = health.takeovers(comments, [], prs, runs=[ci(5, "failure", BOT)])
    red = health.takeovers(comments, [], prs, runs=[ci(5, "failure", RUN)])
    assert [r[4] for r in held] == ["no report"] and [r[4] for r in red] == ["red CI"]
