"""The work of owner sessions is a miss of the improve loop (owner, 2026-10-29): each commit of a run has the trailer
`Agent-Run:` (`claim.mark_commits`), a merge without it is owner work (`dashboard.owner_work`), owner work makes
the process review due after OWNER_GAP merged PRs (`claim.review_slot`), and `framework/tools/health.py` lists it."""
import datetime
import subprocess

import claim
import dashboard
import health

T = datetime.datetime(2026, 10, 29, 12, tzinfo=datetime.timezone.utc)
RUN = "Title\n\nBody\n\nAgent-Run: main\nClaude-Session: https://claude.ai/code/session_1"
OWNER = "Owner change\n\nClaude-Session: https://claude.ai/code/session_2"


def test_a_merge_with_no_run_commit_is_owner_work():
    rows = [(T, 9, f"Owner fix (#9)\n\n{OWNER}"), (T, 8, f"Ticket (#8)\n\n{RUN}"), (T, 7, f"Owner change (#7)\n\n{OWNER}"),
            (T, 6, f"Two commits (#6)\n\n* a\n\n{RUN}\n\n* b"), (T, 5, f"Old (#5)\n\n{OWNER}")]   # newest first
    assert dashboard.owner_work(rows) == [(9, "Owner fix"), (7, "Owner change")]  # #5: before the first marked merge
    assert dashboard.owner_work([(T, 5, "Old (#5)")]) == []                      # no run marks its commits yet


def slot(monkeypatch, merged, owner):
    monkeypatch.setattr(claim, "REVIEW", 100)                                    # test values, not the config
    monkeypatch.setattr(claim, "OWNER_GAP", 20)
    monkeypatch.setattr(claim, "on_github", lambda remote="origin": True)
    monkeypatch.setattr(claim, "api", lambda path: {"body": '<!-- agent-state: {"last_review": "2026-10-29T12:00:00Z"} -->'})
    monkeypatch.setattr(claim, "merged_since", lambda last, gap, remote="origin": merged)
    monkeypatch.setattr(claim, "owner_since", lambda last, remote="origin": owner)
    return claim.review_slot("review")


def test_owner_work_makes_the_process_review_due_early(monkeypatch):
    work = [(7, "Owner change")]
    assert slot(monkeypatch, 20, work) == ("20pr-20261029T120000Z-1", 20)
    assert slot(monkeypatch, 19, work)[0] is None                               # some PRs first: the owner's batch
    assert slot(monkeypatch, 99, [])[0] is None                                 # no owner work: the full gap
    assert slot(monkeypatch, 100, []) == ("100pr-20261029T120000Z-1", 100)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def test_a_run_marks_its_commits_and_keeps_a_foreign_hook(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "a@b.c")
    git(tmp_path, "config", "user.name", "A")
    git(tmp_path, "config", "travel-aggregator.lane", "haiku")
    monkeypatch.chdir(tmp_path)
    claim.mark_commits()
    claim.mark_commits()                                                        # again: still one trailer
    git(tmp_path, "commit", "-q", "--allow-empty", "-m", "Do it\n\nClaude-Session: https://claude.ai/code/x")
    message = git(tmp_path, "log", "-1", "--format=%B")
    assert message.count("Agent-Run: haiku") == 1 and dashboard.RUN_MARK.search(message)
    hook = tmp_path / ".git" / "hooks" / "commit-msg"
    hook.write_text("#!/bin/sh\nexit 0\n")                                     # a hook of another tool
    claim.mark_commits()
    assert hook.read_text() == "#!/bin/sh\nexit 0\n"


def test_health_lists_the_owner_work_and_the_time_waits():
    issues = [{"number": 3, "body": "Start after: 2026-10-30 12:00 UTC", "state": "open"},
              {"number": 4, "body": "Start after: 50 PRs after #1", "state": "open"},
              {"number": 5, "body": "Start after: 2026-10-30", "pull_request": {}}]
    assert health.time_waits(issues) == [3]
    text = health.report(T, [], [], [], [], [], [], owner=[(7, "Owner change")], waits=[3])
    assert "Owner work (merged PRs with no run commit, improve step 0): 1 (#7 Owner change)" in text
    assert "Time waits (open tickets with a date in Start after:): 1 (#3)" in text
    assert "Owner work" not in health.report(T, [], [], [], [], [], [])
