"""framework/tools/ship_pr.py also sees a red check of `[ci] gates` (`agent.toml`; here `browser`) while it waits for the merge (process review
2026-11-02): Automerge needs it green (#221), but the wait ended at the time limit with "Automerge merges it", the run
ended, and a cold run took the red PR over (7 of 10 red CI runs, 5 of 8 takeovers in 100 merged PRs)."""
import dashboard
import ship_pr as ship
from test_ship_pr import fake_github, repo
from test_ship_pr_wait import clock


def test_a_red_gate_ends_the_wait_for_the_merge():
    now, sleep = clock()
    reds = iter([None, None, {"id": 3}])
    assert ship.wait_merge(9, 600, get=lambda n: {"mergeable_state": "blocked"}, now=now, sleep=sleep,
                           red=lambda: next(reds)) == "red"
    assert now() == 2 * ship.POLL


def test_red_gate_takes_only_a_failed_check(monkeypatch):
    monkeypatch.setattr(ship, "GATES", ("browser",))
    runs = {"browser": {"id": 3, "name": "browser", "status": "in_progress", "conclusion": None}}
    monkeypatch.setattr(dashboard, "api", lambda path: {"check_runs": [runs["browser"], {"name": "docker"}]})
    assert ship.red_gate("abc") is None
    runs["browser"] = {"id": 3, "name": "browser", "status": "completed", "conclusion": "success"}
    assert ship.red_gate("abc") is None
    runs["browser"] = {"id": 3, "name": "browser", "status": "completed", "conclusion": "failure"}
    assert ship.red_gate("abc") == runs["browser"]


def test_a_red_browser_check_after_the_green_quick_ci_gives_exit_5(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(repo(tmp_path))
    monkeypatch.setattr(ship, "GATES", ("browser",))
    fake_github(monkeypatch, open_prs=[{"number": 9}])
    api = dashboard.api

    def ci_api(path, method="GET", data=None):
        if path.startswith("commits/") and path.endswith("check-runs?per_page=100"):   # all checks: one call (red_gate)
            return {"check_runs": [{"id": 3, "name": "browser", "status": "completed", "conclusion": "failure"}]}
        if path == "pulls/9":
            return {"mergeable_state": "blocked", "merged": False}
        if path == "actions/jobs/3":
            return {"steps": [{"name": "Browser tests", "conclusion": "failure"}]}
        if path.endswith("/annotations"):
            return [{"annotation_level": "failure", "message": "e2e/book.spec.ts:12 a dancer books"}]
        return api(path, method, data)
    monkeypatch.setattr(dashboard, "api", ci_api)
    monkeypatch.setattr(ship, "state", lambda n: "clean")
    monkeypatch.setattr(ship, "push", lambda n: True)
    assert ship.main(["5", "--tested"]) == 5
    out = capsys.readouterr().out
    assert "quick CI success" in out and "browser CI failure" in out
    assert "failed step: Browser tests" in out and "e2e/book.spec.ts:12" in out
    assert "Automerge merges it" not in out


def test_red_gate_reads_all_gates_in_one_call(monkeypatch):
    monkeypatch.setattr(ship, "GATES", ("browser", "docker", "production"))
    calls = []
    runs = [{"id": 5, "name": "docker", "status": "completed", "conclusion": "failure"},
            {"id": 4, "name": "browser", "status": "completed", "conclusion": "success"},
            {"id": 2, "name": "docker", "status": "completed", "conclusion": "success"}]   # an older run of docker
    monkeypatch.setattr(dashboard, "api", lambda path: calls.append(path) or {"check_runs": runs})
    assert ship.red_gate("abc")["id"] == 5 and len(calls) == 1
    monkeypatch.setattr(ship, "GATES", ())
    assert ship.red_gate("abc") is None and len(calls) == 1
