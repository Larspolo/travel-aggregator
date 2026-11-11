"""framework/tools/ship_pr.py --message: a staged file with an unstaged edit stops the commit (#2402, #2395)."""
import subprocess

import ship_pr as ship
from test_ship_pr import fake_github, repo


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def test_a_staged_file_with_an_unstaged_edit_makes_no_commit(tmp_path, monkeypatch, capsys):
    work = repo(tmp_path, commit=False)
    monkeypatch.chdir(work)
    fake_github(monkeypatch)
    (work / "a.txt").write_text("staged\n")
    _git("add", "a.txt")
    (work / "a.txt").write_text("unstaged\n")
    msg = tmp_path / "msg.txt"
    msg.write_text("Change a\n\nCloses #5\n")
    head = _git("rev-parse", "HEAD")
    assert ship.main(["5", "--message", str(msg), "--tested"]) == 4
    assert "a.txt: staged with unstaged changes" in capsys.readouterr().out
    assert _git("rev-parse", "HEAD") == head


def test_an_unstaged_file_that_is_not_staged_does_not_stop_the_commit(tmp_path, monkeypatch):
    work = repo(tmp_path, commit=False)
    monkeypatch.chdir(work)
    fake_github(monkeypatch)
    monkeypatch.setattr(ship, "push", lambda n: True)
    (work / "a.txt").write_text("staged\n")
    _git("add", "a.txt")
    (work / "logs.txt").write_text("not part of the change\n")
    (work / "a.txt").write_text("staged\n")  # same as the index: no unstaged edit of a.txt
    msg = tmp_path / "msg.txt"
    msg.write_text("Change a\n\nCloses #5\n")
    head = _git("rev-parse", "HEAD")
    body = tmp_path / "body.md"
    body.write_text("What changed.")
    assert ship.partly_staged() == []
    assert ship.main(["5", "--message", str(msg), "--title", "T", "--body", str(body), "--tested"]) == 0
    assert _git("rev-parse", "HEAD") != head
