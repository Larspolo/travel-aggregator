"""ship_pr.py stops the CI wait when the CI run ended with no job quick (#1599)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "framework" / "tools"))
import ship_pr  # noqa: E402


def fake_api(runs):
    def api(path):
        if path.startswith("actions/runs"):
            return {"workflow_runs": runs}
        return {"check_runs": [{"name": "browser (2)", "status": "completed", "conclusion": "failure"}]}
    return api


def run(monkeypatch, runs, capsys):
    monkeypatch.setattr(ship_pr.dashboard, "api", fake_api(runs))
    clock = iter(range(0, 10000, 30))
    sleeps = []
    orig = ship_pr.wait_ci
    monkeypatch.setattr(ship_pr, "wait_ci", lambda sha, dl: orig(sha, dl, now=lambda: next(clock), sleep=sleeps.append))
    code = ship_pr.ci(1564, "e5c120b0", deadline=300)
    return code, capsys.readouterr().out, sleeps


def test_completed_run_with_no_quick_exits_5(monkeypatch, capsys):
    code, out, sleeps = run(monkeypatch, [{"name": "CI", "status": "completed", "conclusion": "failure"}], capsys)
    assert code == 5
    assert "the CI run ended with no job quick: run `merge_main.py --push 1564`" in out
    assert sleeps == []


def test_no_ci_run_yet_still_waits(monkeypatch, capsys):
    code, out, sleeps = run(monkeypatch, [], capsys)
    assert code == 0
    assert "still runs" in out
    assert sleeps
