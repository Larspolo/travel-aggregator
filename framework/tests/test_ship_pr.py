"""framework/tools/ship_pr.py ships a ticket in one call and stops at the first failure (owner, 2026-10-28)."""
import subprocess

import dashboard
import ship_pr as ship


def git(d, *args):
    return subprocess.run(["git", *args], cwd=d, capture_output=True, text=True)


def repo(tmp_path, commit=True):
    """A clone on branch `side` with one commit that is not on origin/main."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(work))
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        git(work, "config", k, v)
    (work / "a.txt").write_text("a\n")
    git(work, "add", "a.txt")
    git(work, "commit", "-qm", "base")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(work, "fetch", "-q", "origin")
    git(work, "checkout", "-qb", "side")
    if commit:
        (work / "a.txt").write_text("b\n")
        git(work, "commit", "-qam", "change")
    return work


def fake_github(monkeypatch, open_prs=(), lint=True):
    calls = []
    if lint:                                            # the lint command of agent.toml: test_ship_pr_lint.py
        monkeypatch.setattr(ship, "lint", lambda: True)

    def api(path, method="GET", data=None):
        calls.append((path, method, data))
        if path.startswith("pulls?head="):
            return list(open_prs)
        if method == "POST":
            return {"number": 9, "html_url": "https://x/9"}
        if path.startswith("commits/"):                  # the quick CI (#4784)
            return {"check_runs": [{"id": 1, "status": "completed", "conclusion": "success"}]}
        return {"mergeable_state": "clean", "merged": True}   # Automerge merged it after the green CI (#5584)
    monkeypatch.setattr(dashboard, "api", api)
    return calls


def test_a_first_push_opens_the_pr_with_its_ticket(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(repo(tmp_path))
    calls = fake_github(monkeypatch)
    pushed = []
    monkeypatch.setattr(ship, "lint", lambda: True)
    monkeypatch.setattr(ship, "push", lambda n: pushed.append(n) or True)
    (tmp_path / "body.md").write_text("What changed.")
    assert ship.main(["5", "--title", "T", "--body", str(tmp_path / "body.md"), "--tested"]) == 0
    post = next(d for p, m, d in calls if m == "POST")
    assert pushed == [5] and post["head"] == "side" and post["body"].endswith("Closes #5\n")
    assert "opened PR #9" in capsys.readouterr().out


def test_failed_checks_stop_before_the_push(tmp_path, monkeypatch):
    monkeypatch.chdir(repo(tmp_path))
    fake_github(monkeypatch, open_prs=[{"number": 9}])
    monkeypatch.setattr(ship, "lint", lambda: True)
    monkeypatch.setattr(ship, "checks", lambda: False)
    monkeypatch.setattr(ship, "push", lambda n: (_ for _ in ()).throw(AssertionError("pushed")))
    assert ship.main(["5"]) == 2


def test_nothing_to_ship(tmp_path, monkeypatch):
    monkeypatch.chdir(repo(tmp_path, commit=False))
    fake_github(monkeypatch)
    assert ship.main(["5", "--tested"]) == 4


def test_a_body_keeps_its_closing_line():
    assert ship.body_with_ticket("Closes #5.", 5) == "Closes #5."
    assert ship.body_with_ticket("Text `closes #5`", 5).endswith("Closes #5\n")      # code does not close (#536)
