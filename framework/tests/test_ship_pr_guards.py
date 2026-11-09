"""ship_pr.py runs the test files whose GUARDS match a changed file, also with --tested (#1328): 6 of 16 red quick CI
runs of 100 merged PRs were whole-app tests (a new route and `tests/test_pages_need_login.py`) that the run skipped."""
import ship_pr as ship
from test_ship_pr import fake_github, git, repo


def guarded_repo(tmp_path, passes):
    work = repo(tmp_path)
    (work / "tests").mkdir()
    (work / "tests" / "test_routes.py").write_text(
        f'GUARDS = ("app/*.py",)\n\n\ndef test_each_route():\n    assert {passes}\n')
    (work / "tests" / "test_other.py").write_text('GUARDS = ("docs/*",)\n\n\ndef test_x():\n    assert False\n')
    git(work, "add", "tests")
    git(work, "commit", "-qm", "tests")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(work, "fetch", "-q", "origin")
    (work / "app").mkdir()
    (work / "app" / "web.py").write_text("ROUTE = 1\n")
    git(work, "add", "app")
    git(work, "commit", "-qm", "route")
    return work


def test_a_failing_guard_file_stops_the_push_also_with_tested(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(guarded_repo(tmp_path, False))
    fake_github(monkeypatch, open_prs=[{"number": 9}])
    monkeypatch.setattr(ship, "push", lambda n: (_ for _ in ()).throw(AssertionError("pushed")))
    assert ship.main(["5", "--tested"]) == 2
    out = capsys.readouterr().out
    assert "tests: tests/test_routes.py" in out and "test_other" not in out


def test_a_passing_guard_file_lets_the_push_go_with_tested(tmp_path, monkeypatch):
    monkeypatch.chdir(guarded_repo(tmp_path, True))
    fake_github(monkeypatch, open_prs=[{"number": 9}])
    pushed = []
    monkeypatch.setattr(ship, "push", lambda n: pushed.append(n) or True)
    assert ship.main(["5", "--tested", "--wait", "0"]) == 0
    assert pushed == [5]
