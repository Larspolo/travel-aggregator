"""framework/tools/ship_pr.py waits for the quick CI of its push and prints the failures (#4784)."""
import dashboard
import ship_pr as ship
from test_ship_pr import fake_github, repo


def check(status="completed", conclusion="success"):
    return {"id": 7, "status": status, "conclusion": conclusion}


def clock():
    t = [0.0]
    return (lambda: t[0]), (lambda s: t.__setitem__(0, t[0] + s))


def test_wait_returns_the_completed_check():
    runs = iter([None, check("queued", None), check()])
    now, sleep = clock()
    assert ship.wait_ci("abc", 600, get=lambda sha: next(runs), now=now, sleep=sleep) == check()
    assert now() == 2 * ship.POLL


def test_wait_stops_at_the_deadline():
    now, sleep = clock()
    assert ship.wait_ci("abc", 100, get=lambda sha: check("in_progress", None), now=now, sleep=sleep) is None
    assert now() <= 100


def fake_ci(monkeypatch, conclusion, open_prs=()):
    calls = fake_github(monkeypatch, open_prs)
    api = dashboard.api

    def ci_api(path, method="GET", data=None):
        if path.startswith("commits/"):
            calls.append((path, method, data))
            return {"check_runs": [check(conclusion=conclusion)]}
        if path.startswith("actions/jobs/"):
            return {"steps": [{"name": "Lint", "conclusion": "success"}, {"name": "Fast tests", "conclusion": "failure"}]}
        if path.endswith("/annotations"):
            return [{"annotation_level": "failure", "message": "FAILED tests/test_x.py::test_y - assert 1 == 2"},
                    {"annotation_level": "failure", "message": "Process completed with exit code 1."},
                    {"annotation_level": "warning", "message": "Node.js 20 is deprecated."}]
        return api(path, method, data)
    monkeypatch.setattr(dashboard, "api", ci_api)
    return calls


def test_red_ci_prints_the_failed_tests(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(repo(tmp_path))
    fake_ci(monkeypatch, "failure", open_prs=[{"number": 9}])
    monkeypatch.setattr(ship, "push", lambda n: True)
    assert ship.main(["5", "--tested"]) == 5
    out = capsys.readouterr().out
    assert "failed step: Fast tests" in out and "FAILED tests/test_x.py::test_y" in out
    assert "Lint" not in out and "Process completed" not in out and "Node.js" not in out


def test_green_ci_ships(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(repo(tmp_path))
    calls = fake_ci(monkeypatch, "success", open_prs=[{"number": 9}])
    monkeypatch.setattr(ship, "push", lambda n: True)
    assert ship.main(["5", "--tested"]) == 0
    head = ship.git("rev-parse", "HEAD").stdout.strip()
    assert (f"commits/{head}/check-runs?check_name=quick", "GET", None) in calls
    assert "quick CI success" in capsys.readouterr().out


def test_no_wait_reads_no_ci(tmp_path, monkeypatch):
    monkeypatch.chdir(repo(tmp_path))
    calls = fake_ci(monkeypatch, "failure", open_prs=[{"number": 9}])
    monkeypatch.setattr(ship, "push", lambda n: True)
    assert ship.main(["5", "--tested", "--wait", "0"]) == 0
    assert not [c for c in calls if c[0].startswith("commits/")]


def test_ci_only_waits_for_the_open_pr(tmp_path, monkeypatch):
    monkeypatch.chdir(repo(tmp_path))
    calls = fake_ci(monkeypatch, "failure", open_prs=[{"number": 9, "head": {"sha": "abc123"}}])
    monkeypatch.setattr(ship, "push", lambda n: (_ for _ in ()).throw(AssertionError("pushed")))
    assert ship.main(["5", "--ci"]) == 5
    assert ("commits/abc123/check-runs?check_name=quick", "GET", None) in calls
