"""`framework/tools/unconflict_pick.py` finds the PRs of `unconflict.yml` with git and few API calls (2026-10-29)."""
import subprocess

import pytest
import unconflict_pick as up

NOW = 1_800_000_000


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """main and three branches: `union` (a conflict that only `merge=union` solves), `text` (a real conflict) and
    `clean` (another file)."""
    run = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    run("init", "-q", "-b", "main")
    run("config", "user.name", "t")
    run("config", "user.email", "t@t")
    (tmp_path / ".gitattributes").write_text("L.md merge=union\n")
    (tmp_path / "L.md").write_text("a\n")
    (tmp_path / "x.py").write_text("x = 1\n")
    run("add", "-A")
    run("commit", "-qm", "base")
    for branch, path, text in (("union", "L.md", "a\npr\n"), ("text", "x.py", "x = 2\n"), ("clean", "y.py", "y\n")):
        run("checkout", "-qb", branch, "main")
        (tmp_path / path).write_text(text)
        run("add", "-A")
        run("commit", "-qm", branch)
    run("checkout", "-q", "main")
    (tmp_path / "L.md").write_text("a\nmain\n")
    (tmp_path / "x.py").write_text("x = 3\n")
    run("commit", "-qam", "main")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_dirty_is_the_conflict_of_github_with_no_merge_attributes(repo):
    assert up.dirty("union", main="main") and up.dirty("text", main="main")
    assert not up.dirty("clean", main="main")
    assert up.has_main("main", main="main") and not up.has_main("clean", main="main")


def pr(n, branch, sha="s", labels=()):
    return {"number": n, "head": {"ref": branch, "sha": sha}, "labels": [{"name": x} for x in labels]}


MAIN_RUNS = [("success", "2026-10-29T14:30:00Z"), ("failure", "2026-10-29T14:00:00Z")]
RED = {"conclusion": "failure", "created_at": "2026-10-29T14:10:00Z"}


def test_pick_takes_dirty_labeled_and_red_by_main_prs_only():
    prs = [pr(1, "claude/a"), pr(2, "claude/b", labels=["conflict"]), pr(3, "claude/c", "s3"),
           pr(4, "claude/d", labels=["hold"]), pr(5, "owner-branch"), pr(6, "claude/f"), pr(7, "ccr-g", "s7"),
           pr(8, "claude/h", "s8")]
    asked = []
    rows = up.pick(prs, MAIN_RUNS, green=True, recent={"s3": RED, "s8": {**RED, "conclusion": "success"}},
                   head_run=lambda sha: asked.append(sha) or RED,
                   is_dirty=lambda b: b == "claude/a", contains_main=lambda b: b == "claude/f",
                   head_time=lambda b: NOW - (60 if b == "claude/b" else 600), now=NOW)
    assert rows == [(1, "claude/a", "s", 0, "dirty"), (3, "claude/c", "s3", 0, "red"), (7, "ccr-g", "s7", 0, "red")]
    assert asked == ["s7"]                              # one call only for a head that the list does not have


def test_no_red_pick_while_main_is_red():
    rows = up.pick([pr(3, "claude/c", "s3")], MAIN_RUNS, green=False, recent={"s3": RED}, head_run=lambda sha: RED,
                   is_dirty=lambda b: False, contains_main=lambda b: False, head_time=lambda b: 0, now=NOW)
    assert rows == []


def test_red_by_main_needs_a_failed_main_run_before_it():
    assert up.red_by_main(RED, MAIN_RUNS)
    assert not up.red_by_main({**RED, "created_at": "2026-10-29T13:00:00Z"}, MAIN_RUNS)   # no main run before it
    assert not up.red_by_main({**RED, "created_at": "2026-10-29T14:40:00Z"}, MAIN_RUNS)   # main was green then
    assert not up.red_by_main(None, MAIN_RUNS)
