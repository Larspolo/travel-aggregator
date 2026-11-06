"""merge_main.py checks a merge of main that the agent committed by hand after exit 1 (#5040)."""
import merge_main
from test_merge_main import BASE, git, repo, tool


def test_a_merge_committed_by_hand_gets_the_checks(tmp_path, monkeypatch):
    d = repo(tmp_path, BASE.replace("LIMIT = 1", "LIMIT = 2"), BASE.replace("LIMIT = 1", "LIMIT = 3"))
    r = tool(d)
    assert r.returncode == 1 and "git commit" not in r.stdout                  # the message says: run the tool again
    (tmp_path / "work" / "t.py").write_text(BASE.replace("LIMIT = 1", "LIMIT = 3"))
    git(d, "commit", "-qam", "merge by hand")
    checked = []
    monkeypatch.chdir(d)
    monkeypatch.setattr(merge_main, "check", lambda conflicted, base: checked.append(conflicted) or False)
    assert merge_main.main([]) == 2 and checked == [["t.py"]]


def test_a_pushed_merge_gets_no_new_checks(tmp_path, monkeypatch):
    d = repo(tmp_path, BASE.replace("LIMIT = 1", "LIMIT = 2"), BASE.replace("LIMIT = 1", "LIMIT = 3"))
    tool(d)
    (tmp_path / "work" / "t.py").write_text(BASE.replace("LIMIT = 1", "LIMIT = 3"))
    git(d, "commit", "-qam", "merge by hand")
    git(d, "push", "-q", "origin", "side")
    checked = []
    monkeypatch.chdir(d)
    monkeypatch.setattr(merge_main, "check", lambda conflicted, base: checked.append(conflicted) or True)
    assert merge_main.main([]) == 0 and checked == []
