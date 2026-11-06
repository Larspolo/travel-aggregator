"""framework/tools/ship_pr.py waits for the merge after the green quick CI: a conflict that Automerge finds then
gives exit 6, so the warm run merges main before it reports (#5584)."""
import dashboard
import ship_pr as ship
from test_ship_pr import fake_github, repo
from test_ship_pr_wait import clock


def reads(*prs):
    it = iter(prs)
    return lambda n: next(it)


def test_the_wait_ends_at_the_merge():
    now, sleep = clock()
    get = reads({"mergeable_state": "clean"}, {"mergeable_state": "unknown"}, {"merged": True})
    assert ship.wait_merge(9, 600, get=get, now=now, sleep=sleep) == "merged"
    assert now() == 2 * ship.POLL


def test_a_conflict_after_the_green_ci_ends_the_wait():
    now, sleep = clock()
    get = reads({"mergeable_state": "clean"}, {"mergeable_state": "dirty"})
    assert ship.wait_merge(9, 600, get=get, now=now, sleep=sleep) == "dirty"


def test_a_held_pr_does_not_wait():
    now, sleep = clock()
    get = reads({"mergeable_state": "clean", "labels": [{"name": "hold"}]})
    assert ship.wait_merge(9, 600, get=get, now=now, sleep=sleep) == "hold"
    assert now() == 0


def test_the_wait_stops_at_the_deadline_after_one_read():
    now, sleep = clock()
    got = []
    assert ship.wait_merge(9, 0, get=lambda n: got.append(n) or {"mergeable_state": "clean"}, now=now, sleep=sleep) == "open"
    assert got == [9]


def fake_merge(monkeypatch, pr, open_prs=()):
    fake_github(monkeypatch, open_prs)
    api = dashboard.api
    monkeypatch.setattr(dashboard, "api", lambda path, method="GET", data=None:
                        pr if path == "pulls/9" and pr.get("merged") is not None else api(path, method, data))
    monkeypatch.setattr(ship, "state", lambda n: "clean")      # the state at the push, before the CI


def test_a_conflict_after_the_green_ci_gives_exit_6(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(repo(tmp_path))
    fake_merge(monkeypatch, {"merged": False, "mergeable_state": "dirty"}, open_prs=[{"number": 9}])
    monkeypatch.setattr(ship, "push", lambda n: True)
    assert ship.main(["5", "--tested"]) == 6
    assert "merge_main.py --push 5" in capsys.readouterr().out


def test_a_takeover_waits_for_the_merge_of_the_pr_branch(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(repo(tmp_path))
    fake_merge(monkeypatch, {"merged": True}, open_prs=[{"number": 9, "head": {"sha": "abc123"}}])
    assert ship.main(["5", "--ci", "--pr-branch", "b"]) == 0
    assert "PR #9: merged" in capsys.readouterr().out


def test_a_conflict_at_the_push_gives_exit_6(tmp_path, monkeypatch):
    monkeypatch.chdir(repo(tmp_path))
    calls = fake_github(monkeypatch, open_prs=[{"number": 9}])
    monkeypatch.setattr(ship, "push", lambda n: True)
    monkeypatch.setattr(ship, "state", lambda n: "dirty")
    assert ship.main(["5", "--tested"]) == 6
    assert not [c for c in calls if c[0].startswith("commits/")]     # GitHub starts no CI on a conflict
