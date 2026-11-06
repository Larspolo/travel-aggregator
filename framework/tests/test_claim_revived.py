"""framework/tools/claim.py: a union merge of main must not bring back the LEARNINGS lines that main removed (#563)."""
import subprocess
import sys

import claim
import pytest
from test_claim import TOOL, run


def write(d, *lines):
    (d / "docs" / "LEARNINGS.md").write_text("".join(f"{x}\n" for x in lines))
    run("git", "commit", "-qam", "change", cwd=d)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A remote with main (lines A, B, C) and a clone on the branch run-1."""
    remote, d = tmp_path / "remote.git", tmp_path / "run"
    run("git", "init", "-q", "--bare", str(remote), cwd=tmp_path)
    run("git", "init", "-q", "-b", "main", str(d), cwd=tmp_path)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        run("git", "config", k, v, cwd=d)
    run("git", "remote", "add", "origin", str(remote), cwd=d)
    (d / "docs").mkdir()
    (d / ".gitattributes").write_text("docs/LEARNINGS.md merge=union\n")
    (d / "docs" / "LEARNINGS.md").write_text("A\nB\nC\n")
    run("git", "add", ".", cwd=d)
    run("git", "commit", "-qm", "base", cwd=d)
    run("git", "push", "-q", "origin", "main", cwd=d)
    run("git", "checkout", "-q", "-b", "run-1", cwd=d)
    write(d, "A", "B", "D", "C")                                  # the ticket adds D next to B
    monkeypatch.chdir(d)
    return d


def main_removes_b(d):
    run("git", "checkout", "-q", "main", cwd=d)
    write(d, "A", "C")                                            # the improve skill moves B out
    run("git", "push", "-q", "origin", "main", cwd=d)
    run("git", "checkout", "-q", "run-1", cwd=d)


def test_union_merge_brings_back_a_removed_line(repo):
    main_removes_b(repo)
    assert claim.revived() == []                                  # not merged yet: the PR merge removes B
    run("git", "merge", "-q", "--no-edit", "origin/main", cwd=repo)
    assert (repo / "docs" / "LEARNINGS.md").read_text().split() == ["A", "B", "D", "C"]
    assert claim.revived() == ["B"]
    write(repo, "A", "D", "C")
    assert claim.revived() == []


def test_own_lines_are_not_revived(repo):
    assert claim.revived() == []
    main_removes_b(repo)
    run("git", "merge", "-q", "--no-edit", "origin/main", cwd=repo)
    write(repo, "A", "D", "C", "E")
    assert claim.revived() == []


def test_guard_names_the_revived_lines(repo):
    assert subprocess.run([sys.executable, TOOL, "9"], cwd=repo).returncode == 0
    main_removes_b(repo)
    run("git", "merge", "-q", "--no-edit", "origin/main", cwd=repo)
    p = subprocess.run([sys.executable, TOOL, "9", "--guard"], cwd=repo, capture_output=True, text=True)
    assert p.returncode == 1 and "B" in p.stdout.splitlines() and "#563" in p.stdout
    write(repo, "A", "D", "C")
    assert subprocess.run([sys.executable, TOOL, "9", "--guard"], cwd=repo).returncode == 0
