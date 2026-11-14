"""framework/tools/usage.py: the work of an owner goes above the weekly pace. The owner answered 8 tickets of this
project, and no run used the answers for 4 hours: the week was ahead, so the target was 0 (2026-11-14)."""
import dashboard
import feedback
import usage

NOW = 1_800_000_000
H = 3600
FIVE = {"five_hour": (0.3, NOW + 2 * H, "allowed")}
AHEAD = FIVE | {"seven_day": (0.52, NOW + 145 * H, "allowed")}          # 52 % used after 23 of 168 hours
PACE = dict(burn7=0.0053, free7=0, week=True, hi=99, share7=1, reserve7=0)


def test_a_week_ahead_gives_a_run_for_the_work_of_an_owner(monkeypatch):
    monkeypatch.setattr(usage, "OWNER_FIRST", 2)
    assert usage.target_runs(AHEAD, NOW, **PACE) == 0
    assert usage.target_runs(AHEAD, NOW, owner=1, **PACE) == 1
    assert usage.target_runs(AHEAD, NOW, owner=5, **PACE) == 2          # not more than the setting
    monkeypatch.setattr(usage, "OWNER_FIRST", 0)                        # the setting 0: the weekly pace decides alone
    assert usage.target_runs(AHEAD, NOW, owner=1, **PACE) == 0


def test_the_work_of_an_owner_is_read_only_when_the_week_gives_no_run(monkeypatch):
    monkeypatch.setattr(usage, "OWNER_FIRST", 1)
    calls = []
    behind = FIVE | {"seven_day": (0.2, NOW + 4 * 86400, "allowed")}    # 20 % used after 43 % of the week

    def owner():
        calls.append(1)
        return 1
    assert usage.target_runs(behind, NOW, owner=owner, **PACE) == usage.target_runs(behind, NOW, **PACE) > 1
    assert not calls
    assert usage.target_runs(AHEAD, NOW, owner=owner, **PACE) == 1 and calls == [1]


def test_a_rejected_limit_stays_at_no_run(monkeypatch):
    monkeypatch.setattr(usage, "OWNER_FIRST", 1)
    assert usage.target_runs(AHEAD | {"seven_day": (1.0, NOW + H, "rejected")}, NOW, owner=1, **PACE) == 0
    assert usage.target_runs({"five_hour": (1.0, NOW + 600, "rejected")}, NOW, owner=1, **PACE) == 0


def test_owner_wait_counts_a_comment_with_no_answer_and_an_issue_with_no_label(monkeypatch):
    def wait():
        usage.owner_wait.cache_clear()
        try:
            return usage.owner_wait()
        finally:
            usage.owner_wait.cache_clear()
    pull = {"number": 4, "labels": [], "pull_request": {}}
    monkeypatch.setattr(dashboard, "pages", lambda path: [{"number": 3, "labels": [{"name": "P2"}]}, pull])
    monkeypatch.setattr(feedback, "fetch", lambda: [{"id": 1}])
    assert wait() == 1                                                   # a comment of an owner with no answer
    monkeypatch.setattr(feedback, "fetch", lambda: [])
    assert wait() == 0                                                   # a PR with no label is no new ticket
    monkeypatch.setattr(dashboard, "pages", lambda path: [{"number": 3, "labels": []}, pull])
    assert wait() == 1                                                   # a new issue that no run triaged

    def fail():
        raise OSError("no network")
    monkeypatch.setattr(feedback, "fetch", fail)
    assert wait() == 0                                                   # a read error: the weekly pace decides
